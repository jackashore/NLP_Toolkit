# -*- coding: utf-8 -*-
"""
Created on Mon Jul  8 09:09:18 2019

@author: WT
"""
import os
import pickle
import torch
import numpy as np

from google.cloud import translate_v3beta1 as translate

def load_pickle(filename):
    completeName = os.path.join("./data/",\
                                filename)
    with open(completeName, 'rb') as pkl_file:
        data = pickle.load(pkl_file)
    return data

def save_as_pickle(filename, data):
    completeName = os.path.join("./data/",\
                                filename)
    with open(completeName, 'wb') as output:
        pickle.dump(data, output)

# code from AllenNLP
class CosineWithRestarts(torch.optim.lr_scheduler._LRScheduler):
    """
    Cosine annealing with restarts.
    Parameters
    ----------
    optimizer : torch.optim.Optimizer
    T_max : int
        The maximum number of iterations within the first cycle.
    eta_min : float, optional (default: 0)
        The minimum learning rate.
    last_epoch : int, optional (default: -1)
        The index of the last epoch.
    """

    def __init__(self,
                 optimizer: torch.optim.Optimizer,
                 T_max: int,
                 eta_min: float = 0.,
                 last_epoch: int = -1,
                 factor: float = 1.) -> None:
        # pylint: disable=invalid-name
        self.T_max = T_max
        self.eta_min = eta_min
        self.factor = factor
        self._last_restart: int = 0
        self._cycle_counter: int = 0
        self._cycle_factor: float = 1.
        self._updated_cycle_len: int = T_max
        self._initialized: bool = False
        super(CosineWithRestarts, self).__init__(optimizer, last_epoch)

    def get_lr(self):
        """Get updated learning rate."""
        # HACK: We need to check if this is the first time get_lr() was called, since
        # we want to start with step = 0, but _LRScheduler calls get_lr with
        # last_epoch + 1 when initialized.
        if not self._initialized:
            self._initialized = True
            return self.base_lrs

        step = self.last_epoch + 1
        self._cycle_counter = step - self._last_restart

        lrs = [
            (
                self.eta_min + ((lr - self.eta_min) / 2) *
                (
                    np.cos(
                        np.pi *
                        ((self._cycle_counter) % self._updated_cycle_len) /
                        self._updated_cycle_len
                    ) + 1
                )
            ) for lr in self.base_lrs
        ]

        if self._cycle_counter % self._updated_cycle_len == 0:
            # Adjust the cycle length.
            self._cycle_factor *= self.factor
            self._cycle_counter = 0
            self._updated_cycle_len = int(self._cycle_factor * self.T_max)
            self._last_restart = step

        return lrs
    
class google_translate_api(object):
    def __init__(self, project_id="zh-en-translatio-1571230525546"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = '/home/weetee/Desktop/Repositories/NLP_Text/NLP_Toolkit/data/translation/zh-en-translatio-1571230525546-2b50bf5c50cb.json'
        self.client = translate.TranslationServiceClient()
        self.project_id = project_id
        self.location = 'global'
        self.parent = self.client.location_path(self.project_id, self.location)
        
    def translate(self, sent, src="en-US", trg="zh"):
        self.response = self.client.translate_text(
                                        parent=self.parent,
                                        contents=[sent],
                                        mime_type='text/plain',  # mime types: text/plain, text/html
                                        source_language_code=src,
                                        target_language_code=trg)
                                    
        for translation in self.response.translations:
            print('Translated Text: {}'.format(translation))
        return self.response.translations
        