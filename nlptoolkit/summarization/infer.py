# -*- coding: utf-8 -*-
"""
Created on Tue Aug 13 09:17:59 2019

@author: WT
"""
import pandas as pd
import torch
from torch.autograd import Variable
from .preprocessing_funcs import load_dataloaders
from .models.InputConv_Transformer import create_masks
from .train_funcs import load_model_and_optimizer
from .utils.bpe_vocab import Encoder
from .utils.misc_utils import load_pickle
from tqdm import tqdm
import time
import logging

tqdm.pandas(desc="prog_bar")
logging.basicConfig(format='%(asctime)s [%(levelname)s]: %(message)s', \
                    datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO)
logger = logging.getLogger('__file__')

class infer_from_trained(object):
    def __init__(self, args=None):
        if args is None:
            self.args = load_pickle("args.pkl")
        else:
            self.args = args
        self.cuda = torch.cuda.is_available()
        self.args.batch_size = 1
        
        logger.info("Loading tokenizer and model...")
        try:
            train_loader, train_length, max_features_length, max_seq_len = load_dataloaders(self.args)
            self.train_loader = train_loader
        except Exception as e:
            print(e)
            print("Data loading error!")
            max_features_length = self.args.max_features_length
            max_seq_len = self.args.max_features_length
            self.train_loader = None
        
        self.max_features_length = max_features_length
        self.max_seq_len = max_seq_len
        
        if (self.args.level == "word") or (self.args.level == "char"):
            vocab = load_pickle("vocab.pkl")
            vocab_size = len(vocab.w2idx)
            trg_init = vocab.w2idx["<sos>"]
        elif self.args.level == "bpe":
            vocab = Encoder.load("./data/vocab.pkl")
            vocab_size = vocab.vocab_size
            trg_init = vocab.word_vocab["__sos"]
        
        self.trg_init = Variable(torch.LongTensor([trg_init])).unsqueeze(0)
        
        self.vocab = vocab
        self.vocab_size = vocab_size
        
        logger.info("Max features length = %d %ss" % (max_features_length, self.args.level))
        logger.info("Vocabulary size: %d" % vocab_size)
        
        logger.info("Loading model and optimizers...")
        
        if self.args.fp16:    
            from apex import amp
        else:
            amp = None
            
        net, criterion, optimizer, scheduler, start_epoch, acc = load_model_and_optimizer(self.args, self.vocab_size, self.max_features_length,\
                                                                                          self.max_seq_len, self.cuda, amp)
        self.net = net
        self.net.eval()
        
    def infer_from_data(self):
        if self.train_loader is not None:
            with torch.no_grad():
                for i, data in enumerate(self.train_loader):
                    
                    if self.args.model_no == 0:
                        src_input, trg_input = data[0], data[1][:, :-1]
                        labels = data[1][:,1:].contiguous().view(-1)
                        src_mask, trg_mask = create_masks(src_input, trg_input)
                        if self.cuda:
                            src_input = src_input.cuda().long(); trg_input = trg_input.cuda().long(); labels = labels.cuda().long()
                            src_mask = src_mask.cuda(); trg_mask = trg_mask.cuda()
                        outputs = self.net(src_input, trg_input[:,0].unsqueeze(0), src_mask, trg_mask, infer=True)
                        
                    elif self.args.model_no == 1:
                        src_input, trg_input = data[0], data[1][:, :-1]
                        labels = data[1][:,1:].contiguous().view(-1)
                        if self.cuda:
                            src_input = src_input.cuda().long(); trg_input = trg_input.cuda().long(); labels = labels.cuda().long()
                        outputs = self.net(src_input, trg_input[:,0].unsqueeze(0), infer=True)
                    #outputs = outputs.view(-1, outputs.size(-1))
                    #print(outputs.shape)
                    
                    if (self.args.level == "word") or (self.args.level == "char"):
                        vocab_decoder = self.vocab.convert_idx2w
                    elif self.args.level == "bpe":
                        vocab_decoder = self.vocab.inverse_transform
                    
                    if self.cuda:
                        l = list(labels.cpu().numpy())
                        #o = list(torch.softmax(outputs, dim=1).max(1)[1].cpu().numpy())
                        o = outputs[0].cpu().numpy().tolist()
                    else:
                        l = list(labels.numpy())
                        #o = list(torch.softmax(outputs, dim=1).max(1)[1].numpy())
                        o = outputs[0].numpy().tolist()
                        
                    if self.args.level == "bpe":
                        l = [l]
                        o = [o]
                    #print(o)
                    print("Sample Output: ", " ".join(vocab_decoder(o)))
                    print("Sample Label: ", " ".join(vocab_decoder(l)))
                    print("")
                    time.sleep(7)
        else:
            print("No data to infer!")
            
    def infer_sentence(self, sent):
        return
    
    def infer_from_input(self):
        self.net.eval()
        while True:
            user_input = input("Type input sentence (Type \'exit' or \'quit' to quit):\n")
            if user_input in ["exit", "quit"]:
                break
            predicted = self.infer_sentence(user_input)
        return predicted
    
    def infer_from_file(self, in_file="./data/input.txt", out_file="./data/output.txt"):
        df = pd.read_csv(in_file, header=None, names=["sents"])
        df['labels'] = df.progress_apply(lambda x: self.infer_sentence(x['sents']), axis=1)
        df.to_csv(out_file, index=False)
        logger.info("Done and saved as %s!" % out_file)
        return

def infer(args, from_data=False):
    args.batch_size = 1
    cuda = torch.cuda.is_available()
    train_loader, train_length, max_features_length, max_seq_len = load_dataloaders(args)
    
    if (args.level == "word") or (args.level == "char"):
        vocab = load_pickle("vocab.pkl")
        vocab_size = len(vocab.w2idx)
        trg_init = vocab.w2idx["<sos>"]
    elif args.level == "bpe":
        vocab = Encoder.load("./data/vocab.pkl")
        vocab_size = vocab.vocab_size
        trg_init = vocab.word_vocab["__sos"]
    trg_init = Variable(torch.LongTensor([trg_init])).unsqueeze(0)
        
    logger.info("Max features length = %d %ss" % (max_features_length, args.level))
    logger.info("Vocabulary size: %d" % vocab_size)
    
    logger.info("Loading model and optimizers...")
    if args.fp16:    
        from apex import amp
    else:
        amp = None
    net, criterion, optimizer, scheduler, start_epoch, acc = load_model_and_optimizer(args, vocab_size, max_features_length,\
                                                                                      max_seq_len, cuda, amp)
    
    
    if from_data:
        with torch.no_grad():
            for i, data in enumerate(train_loader):
                
                if args.model_no == 0:
                    src_input, trg_input = data[0], data[1][:, :-1]
                    labels = data[1][:,1:].contiguous().view(-1)
                    src_mask, trg_mask = create_masks(src_input, trg_input)
                    if cuda:
                        src_input = src_input.cuda().long(); trg_input = trg_input.cuda().long(); labels = labels.cuda().long()
                        src_mask = src_mask.cuda(); trg_mask = trg_mask.cuda()
                    outputs = net(src_input, trg_input[:,0].unsqueeze(0), src_mask, trg_mask, infer=True)
                    
                elif args.model_no == 1:
                    src_input, trg_input = data[0], data[1][:, :-1]
                    labels = data[1][:,1:].contiguous().view(-1)
                    if cuda:
                        src_input = src_input.cuda().long(); trg_input = trg_input.cuda().long(); labels = labels.cuda().long()
                    outputs = net(src_input, trg_input[:,0].unsqueeze(0), infer=True)
                #outputs = outputs.view(-1, outputs.size(-1))
                #print(outputs.shape)
                
                if (args.level == "word") or (args.level == "char"):
                    vocab_decoder = vocab.convert_idx2w
                elif args.level == "bpe":
                    vocab_decoder = vocab.inverse_transform
                
                if cuda:
                    l = list(labels.cpu().numpy())
                    #o = list(torch.softmax(outputs, dim=1).max(1)[1].cpu().numpy())
                    o = outputs[0].cpu().numpy().tolist()
                else:
                    l = list(labels.numpy())
                    #o = list(torch.softmax(outputs, dim=1).max(1)[1].numpy())
                    o = outputs[0].numpy().tolist()
                    
                if args.level == "bpe":
                    l = [l]
                    o = [o]
                #print(o)
                print("Sample Output: ", " ".join(vocab_decoder(o)))
                print("Sample Label: ", " ".join(vocab_decoder(l)))
                print("")
                time.sleep(7)
    else:
        pass