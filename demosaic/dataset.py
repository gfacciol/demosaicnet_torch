import logging
import os
import struct
import re
import time

import numpy as np
import skimage.io as skio
import torch as th
# from scipy.stats import ortho_group
from skimage.color import rgb2hsv, hsv2rgb

from torch.utils.data import Dataset
from torchlib.image import read_pfm
from torchlib.utils import Timer

log = logging.getLogger("demosaic_data")

class SRGB2Linear(object):
  def __init__(self):
    super(SRGB2Linear, self).__init__()
    self.a = 0.055
    self.thresh = 0.04045
    self.scale = 12.92
    self.gamma = 2.4

  def __call__(self, im):
    return np.where(im <= self.thresh,
                    im / self.scale,
                    np.power((im + self.a) / (1 + self.a), self.gamma))

def bayer_mosaic(im):
  """GRBG Bayer mosaic."""

  mos = np.copy(im)

  # red
  mos[0, ::2, 0::2] = 0
  mos[0, 1::2, :] = 0

  # green
  mos[1, ::2, 1::2] = 0
  mos[1, 1::2, ::2] = 0

  # blue
  mos[2, 0::2, :] = 0
  mos[2, 1::2, 1::2] = 0

  return mos

def xtrans_mosaic(im):
  """XTrans Mosaick.

     G b G G r G
     r G r b G b
     G b G G r G
     G r G G b G
     b G b r G r
     G r G G b G
  """
  mask = np.zeros((3, 6, 6), dtype=np.float32)
  g_pos = [(0,0), (0,2), (0,3), (0,5),
           (1,1), (1,4),
           (2,0), (2,2), (2,3), (2,5),
           (3,0), (3,2), (3,3), (3,5), 
           (4,1), (4,4), 
           (5,0), (5,2), (5,3), (5,5)]
  r_pos = [(0,4), 
           (1,0), (1,2), 
           (2,4), (3,1), 
           (4,3), (4,5), 
           (5,1)]
  b_pos = [(0,1), 
           (1,3), (1,5), 
           (2,1), 
           (3,4), 
           (4,0), (4,2), 
           (5,4)]

  for y, x in g_pos:
    mask[1, y, x] = 1

  for y, x in r_pos:
    mask[0, y, x] = 1

  for y, x in b_pos:
    mask[2, y, x] = 1

  mos = np.copy(im)

  _, h, w = mos.shape
  mask = np.tile(mask, [1, np.ceil(h / 6).astype(np.int32), np.ceil(w / 6).astype(np.int32)])
  mask = mask[:, :h, :w]

  return mask*mos



class DemosaicDataset(Dataset):
  def __init__(self, filelist, add_noise=False, max_noise=0.1, transform=None, 
               augment=False):
    self.transform = transform

    self.add_noise = add_noise
    self.max_noise = max_noise

    self.augment = augment

    self.linearizer = SRGB2Linear()

    if not os.path.splitext(filelist)[-1] == ".txt":
      raise ValueError("Dataset should be speficied as a .txt file")

    self.root = os.path.dirname(filelist)
    self.images = []
    with open(filelist) as fid:
      for l in fid.readlines():
        im = l.strip()
        self.images.append(os.path.join(self.root, im))
    self.count = len(self.images)

  def __len__(self):
    return self.count

  def make_mosaic(self, im):
    return NotImplemented

  def __getitem__(self, idx):
    impath = self.images[idx]

    # read image
    im = skio.imread(impath).astype(np.float32) / 255.0

    # im = self.linearizer(im)

    if self.augment:
      if np.random.uniform() < 0.5:
        im = np.fliplr(im)
      if np.random.uniform() < 0.5:
        im = np.flipud(im)

      im = np.rot90(im, k=np.random.randint(0, 4))

      # Pixel shift
      if np.random.uniform() < 0.5:
        im = np.roll(im, 1, 0)
      if np.random.uniform() < 0.5:
        im = np.roll(im, 1, 1)

      if np.random.uniform() < 0.5:
        shift = np.random.uniform(-0.1, 0.1)
        im = rgb2hsv(im)
        im[:, :, 0] = np.mod(im[:, :, 0] + shift, 1)
        im = hsv2rgb(im)

      # Randomize exposure
      if np.random.uniform() < 0.5:
        im *= np.random.uniform(0.5, 1.2)

      im = np.clip(im, 0, 1)

      im = np.ascontiguousarray(im).astype(np.float32)

    im = np.transpose(im, [2, 1, 0])

    # add noise
    std = 0
    if self.add_noise:
      std = np.random.uniform(0, self.max_noise)
      im += np.random.normal(0, std, size=im.shape)
      im = np.clip(im, 0, 1)

    # apply mosaic
    mosaic = self.make_mosaic(im)

    sample = {
        "mosaic": mosaic,
        "noise_variance": np.array([std]),
        "target": im,
        }

    # Augment
    if self.transform is not None:
      sample = self.transform(sample)

    return sample

  def __repr__(self):
    s = "Dataset\n"
    s += "  . {} images\n".format(len(self.images))
    return s


class ToBatch(object):
  def __call__(self, sample):
    for k in sample.keys():
      if type(sample[k]) == np.ndarray:
        sample[k] = np.expand_dims(sample[k], 0)
    return sample


class ToTensor(object):
  def __call__(self, sample):
    for k in sample.keys():
      if type(sample[k]) == np.ndarray:
        sample[k] = th.from_numpy(sample[k])
    return sample


class BayerDataset(DemosaicDataset):
  def make_mosaic(self, im):
    return bayer_mosaic(im)


class XtransDataset(DemosaicDataset):
  def make_mosaic(self, im):
    return xtrans_mosaic(im)
