#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Nov 28 09:37:26 2019

@author: weetee
"""
import os
import math
import torch
import torch.nn as nn
from ..misc import save_as_pickle, load_pickle
#from seqeval.metrics import f1_score, recall_score, precision_score
import logging
from tqdm import tqdm
import numpy as np

# alternate eval
from sklearn.preprocessing import MultiLabelBinarizer
from sklearn.metrics import precision_score, recall_score, f1_score, classification_report

logging.basicConfig(format='%(asctime)s [%(levelname)s]: %(message)s', \
                    datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO)
logger = logging.getLogger(__file__)

def load_state(net, optimizer, scheduler, args, load_best=False):
    """ Loads saved model and optimizer states if exists """
    base_path = "./data/"
    amp_checkpoint = None
    checkpoint_path = os.path.join(base_path,"task_test_checkpoint_%d.pth.tar" % args.model_no)
    best_path = os.path.join(base_path,"task_test_model_best_%d.pth.tar" % args.model_no)
    start_epoch, best_pred, checkpoint = 0, 0, None
    if (load_best == True) and os.path.isfile(best_path):
        checkpoint = torch.load(best_path)
        logger.info("Loaded best model.")
    elif os.path.isfile(checkpoint_path):
        checkpoint = torch.load(checkpoint_path)
        logger.info("Loaded checkpoint model.")
    if checkpoint != None:
        start_epoch = checkpoint['epoch']
        best_pred = checkpoint['best_acc']
        net.load_state_dict(checkpoint['state_dict'])
        if optimizer is not None:
            optimizer.load_state_dict(checkpoint['optimizer'])
        if scheduler is not None:
            scheduler.load_state_dict(checkpoint['scheduler'])
        amp_checkpoint = checkpoint['amp']
        logger.info("Loaded model and optimizer.")    
    return start_epoch, best_pred, amp_checkpoint

def load_results(model_no=0):
    """ Loads saved results if exists """
    losses_path = "./data/task_test_losses_per_epoch_%d.pkl" % model_no
    accuracy_path = "./data/task_train_accuracy_per_epoch_%d.pkl" % model_no
    f1_path = "./data/task_test_f1_per_epoch_%d.pkl" % model_no
    if os.path.isfile(losses_path) and os.path.isfile(accuracy_path) and os.path.isfile(f1_path):
        losses_per_epoch = load_pickle("task_test_losses_per_epoch_%d.pkl" % model_no)
        accuracy_per_epoch = load_pickle("task_train_accuracy_per_epoch_%d.pkl" % model_no)
        f1_per_epoch = load_pickle("task_test_f1_per_epoch_%d.pkl" % model_no)
        logger.info("Loaded results buffer")
    else:
        losses_per_epoch, accuracy_per_epoch, f1_per_epoch = [], [], []
    return losses_per_epoch, accuracy_per_epoch, f1_per_epoch


def evaluate_(output, labels, ignore_idx):
    ### ignore index 0 (padding) when calculating accuracy
    idxs = (labels != ignore_idx).squeeze()
    o_labels = torch.softmax(output, dim=1).max(1)[1]
    l = labels.squeeze()[idxs]; o = o_labels[idxs]

    if len(idxs) > 1:
        acc = (l == o).sum().item()/len(idxs)
    else:
        acc = (l == o).sum().item()
    l = l.cpu().numpy().tolist() if l.is_cuda else l.numpy().tolist()
    o = o.cpu().numpy().tolist() if o.is_cuda else o.numpy().tolist()

    return acc, (o, l)

def evaluate_results(net, test_loader, pad_id, cuda):
    logger.info("Evaluating test samples...")
    acc = 0; out_labels = []; true_labels = []
    net.eval()

    # alternate eval
    multi = MultiLabelBinarizer()

    with torch.no_grad():
        for i, data in tqdm(enumerate(test_loader), total=len(test_loader)):
            x, e1_e2_start, labels, _,_,_ = data
            attention_mask = (x != pad_id).float()
            token_type_ids = torch.zeros((x.shape[0], x.shape[1])).long()

            if cuda:
                x = x.cuda()
                labels = labels.cuda()
                attention_mask = attention_mask.cuda()
                token_type_ids = token_type_ids.cuda()
                
            classification_logits = net(x, token_type_ids=token_type_ids, attention_mask=attention_mask, Q=None,\
                          e1_e2_start=e1_e2_start)
            
            accuracy, (o, l) = evaluate_(classification_logits, labels, ignore_idx=-1)
            out_labels.append([str(i) for i in o]); true_labels.append([str(i) for i in l])
            acc += accuracy
    
    # alternate eval
    #true_new = multi.fit(true_labels).transform(true_labels)
    #out_new = multi.transform(out_labels)
    true_new = []
    for n in true_labels:
        for val in n:
            true_new.append(val)
    out_new = []
    for n2 in out_labels:
        for val2 in n2:
            out_new.append(val2)

    logger.info("**********************LEN PREDICTIONS********************")
    logger.info(len(true_labels))
    logger.info(len(true_new))
    #print(true_new)
    #print(out_new)
    accuracy = acc/(i + 1)
    results = {
        "accuracy": accuracy,
        "precision": precision_score(true_new, out_new, average='weighted'),
        "recall": recall_score(true_new, out_new, average='weighted'),
        "f1": f1_score(true_new, out_new, average='weighted'),
        "report": classification_report(true_new, out_new)
    }
    logger.info("***** Eval results *****")
    for key in sorted(results.keys()):
        logger.info("  %s = %s", key, str(results[key]))
    
    return results
    
