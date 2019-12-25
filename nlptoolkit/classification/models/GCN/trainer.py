# -*- coding: utf-8 -*-
import os
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from .train_funcs import load_datasets, load_state, load_results, evaluate, infer
from .GCN import gcn
from .preprocessing_funcs import load_pickle, save_as_pickle
import matplotlib.pyplot as plt
import logging
from sklearn.metrics import *

logging.basicConfig(format='%(asctime)s [%(levelname)s]: %(message)s', \
                    datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO)
logger = logging.getLogger(__file__)


def metrics(output, labels_e):
    if len(labels_e) == 0:
        return (0, 0, 0)
    else:
        _, labels = output.max(1);
        labels = labels.cpu().numpy() if labels.is_cuda else labels.numpy()
        recall = recall_score(labels, labels_e, average="macro")
        precision = precision_score(labels, labels_e, average="macro")
        f1 = f1_score(labels, labels_e, average="macro")
        return (recall, precision, f1)


def train_and_fit(args):
    cuda = torch.cuda.is_available()

    f, X, A_hat, selected, labels_selected, labels_not_selected, test_idxs = load_datasets(args,
                                                                                           train_test_split=args.train_test_split)
    targets = torch.tensor(labels_selected).long()
    # print(labels_selected, labels_not_selected)
    net = gcn(X.shape[1], A_hat, cuda, args)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(net.parameters(), lr=args.lr)
    scheduler = optim.lr_scheduler.MultiStepLR(optimizer, milestones=[1000, 2000, 3000, 4000, 5000, 6000], gamma=0.77)

    start_epoch, best_pred = load_state(net, optimizer, scheduler, model_no=args.model_no, load_best=False)
    losses_per_epoch, evaluation_trained, evaluation_untrained = load_results(model_no=args.model_no)

    if cuda:
        net.cuda()
        optimizer = optim.Adam(net.parameters(), lr=args.lr)
        f = f.cuda()
        targets = targets.cuda()

    logger.info("Starting training process...")
    net.train()
    for e in range(start_epoch, args.num_epochs):
        optimizer.zero_grad()
        output = net(f)
        loss = criterion(output[selected], targets)
        losses_per_epoch.append(loss.item())
        loss.backward()
        optimizer.step()
        if e % 50 == 0:
            # print(output[selected]); print(targets)
            ### Evaluate other untrained nodes and check accuracy of labelling
            net.eval()
            with torch.no_grad():
                pred_labels = net(f)
                train_metrics = metrics(pred_labels[selected], labels_selected);
                untrained_metrics = metrics(pred_labels[test_idxs], labels_not_selected)
                trained_accuracy = evaluate(pred_labels[selected], labels_selected);
                untrained_accuracy = evaluate(pred_labels[test_idxs], labels_not_selected)
            evaluation_trained.append((e, trained_accuracy));
            evaluation_untrained.append((e, untrained_accuracy))
            print("[Epoch %d]: Loss: %.7f" % (e, losses_per_epoch[-1]))
            print("Evaluation accuracy of trained nodes: %.7f" % (trained_accuracy))
            print("Evaluation recall, precision, f1-score of trained nodes: {:.3f}, {:.3f}, {:.3f}".format(
                train_metrics[0], train_metrics[1], train_metrics[2]))
            print("Evaluation accuracy of test nodes: %.7f" % (
                untrained_accuracy))
            print("Evaluation recall, precision, f1-score of test nodes: {:.3f}, {:.3f}, {:.3f}".format(
                untrained_metrics[0], untrained_metrics[1], untrained_metrics[2]))
            print("Labels of trained nodes: \n", output[selected].max(1)[1])
            net.train()
            if trained_accuracy > best_pred:
                best_pred = trained_accuracy
                torch.save({
                    'epoch': e + 1, \
                    'state_dict': net.state_dict(), \
                    'best_acc': trained_accuracy, \
                    'optimizer': optimizer.state_dict(), \
                    'scheduler': scheduler.state_dict(), \
                    }, os.path.join("./data/", \
                                    "test_model_best_%d.pth.tar" % args.model_no))
        if (e % 250) == 0:
            save_as_pickle("test_losses_per_epoch_%d.pkl" % args.model_no, losses_per_epoch)
            save_as_pickle("test_accuracy_per_epoch_%d.pkl" % args.model_no, evaluation_untrained)
            save_as_pickle("train_accuracy_per_epoch_%d.pkl" % args.model_no, evaluation_trained)
            torch.save({
                'epoch': e + 1, \
                'state_dict': net.state_dict(), \
                'best_acc': trained_accuracy, \
                'optimizer': optimizer.state_dict(), \
                'scheduler': scheduler.state_dict(), \
                }, os.path.join("./data/", \
                                "test_checkpoint_%d.pth.tar" % args.model_no))
        scheduler.step()

    logger.info("Finished training!")
    evaluation_trained = np.array(evaluation_trained);
    evaluation_untrained = np.array(evaluation_untrained)
    save_as_pickle("test_losses_per_epoch_%d_final.pkl" % args.model_no, losses_per_epoch)
    save_as_pickle("train_accuracy_per_epoch_%d_final.pkl" % args.model_no, evaluation_trained)
    save_as_pickle("test_accuracy_per_epoch_%d_final.pkl" % args.model_no, evaluation_untrained)

    fig = plt.figure(figsize=(13, 13))
    ax = fig.add_subplot(111)
    ax.scatter([i for i in range(len(losses_per_epoch))], losses_per_epoch)
    ax.set_xlabel("Epoch", fontsize=15)
    ax.set_ylabel("Loss", fontsize=15)
    ax.set_title("Loss vs Epoch", fontsize=20)
    plt.savefig(os.path.join("./data/", "loss_vs_epoch_%d.png" % args.model_no))

    fig = plt.figure(figsize=(13, 13))
    ax = fig.add_subplot(111)
    ax.scatter(evaluation_trained[:, 0], evaluation_trained[:, 1])
    ax.set_xlabel("Epoch", fontsize=15)
    ax.set_ylabel("Accuracy on trained nodes", fontsize=15)
    ax.set_title("Accuracy (trained nodes) vs Epoch", fontsize=20)
    plt.savefig(os.path.join("./data/", "trained_accuracy_vs_epoch_%d.png" % args.model_no))

    if len(labels_not_selected) > 0:
        fig = plt.figure(figsize=(13, 13))
        ax = fig.add_subplot(111)
        ax.scatter(evaluation_untrained[:, 0], evaluation_untrained[:, 1])
        ax.set_xlabel("Epoch", fontsize=15)
        ax.set_ylabel("Accuracy on untrained nodes", fontsize=15)
        ax.set_title("Accuracy (untrained nodes) vs Epoch", fontsize=20)
        plt.savefig(os.path.join("./data/", "untrained_accuracy_vs_epoch_%d.png" % args.model_no))

        fig = plt.figure(figsize=(13, 13))
        ax = fig.add_subplot(111)
        ax.scatter(evaluation_trained[:, 0], evaluation_trained[:, 1], c="red", marker="v", \
                   label="Trained Nodes")
        ax.scatter(evaluation_untrained[:, 0], evaluation_untrained[:, 1], c="blue", marker="o", \
                   label="Untrained Nodes")
        ax.set_xlabel("Epoch", fontsize=15)
        ax.set_ylabel("Accuracy", fontsize=15)
        ax.set_title("Accuracy vs Epoch", fontsize=20)
        ax.legend(fontsize=20)
        plt.savefig(os.path.join("./data/", "combined_plot_accuracy_vs_epoch_%d.png" % args.model_no))

    infer(f, test_idxs, net)