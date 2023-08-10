"""
Configuration for train

You can check the essential information,
and if you want to change model structure or training method,
you have to change this file.
"""
#######################################################################
#                               path                                  #
#######################################################################
expmt_name = 'MODEL_SAVE_DIR_NAME'
job_dir = './models/' + expmt_name
logs_dir = './logs/' + expmt_name

# if you have a pretrained model,
# write the directory path for your pretrained model
pretrained_addr = 'PRETRAINED_MODEL_DIR_NAME'
chkpt_num = 1  # and check point number

#######################################################################
#                        speech data setting                          #
#######################################################################
# for data(feature) extraction
FS = 16000
WIN_LEN = 400
HOP_LEN = 100
FFT_LEN = 512
FRAME_SEC = WIN_LEN / FS

# dataset path
noisy_dirs_for_train = './Dataset/train/noisy/'
clean_dirs_for_train = './Dataset/train/clean/'
noisy_dirs_for_valid = './Dataset/valid/noisy/'
clean_dirs_for_valid = './Dataset/valid/clean/'

#######################################################################
#                           hyperparameters                           #
#######################################################################
max_epoch = 5
batch = 1
learning_rate = 0.001
joint_loss = True

DEVICE = 'cpu'

model_type = ['Baseline', 'Proposed']
model_mode = model_type[1]
