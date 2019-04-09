Pytorch implementation (using pretrained weights) of:

     Deep Joint Demosaicking and Denoisingi, SiGGRAPH Asia 2016.
     Michaël Gharbi, Gaurav Chaurasia, Sylvain Paris, Frédo Durand

based on <https://github.com/mgharbi/demosaicnet_torch> and <https://github.com/mgharbi/demosaicnet_caffe>

Exaple call (result is saved in output):

     python3 ./demosaicnet.py --input data/36111627_7991189675.jpg --output output --noise 0.01 
