# configuration for train

expmt_name = 'MODEL_SAVE_DIR_NAME'
job_dir = './models/' + expmt_name
logs_dir = './logs/' + expmt_name

FS = 16000
WIN_LEN = 400
HOP_LEN = 100
FFT_LEN = 512
FRAME_SEC = WIN_LEN / FS

noisy_dirs_for_train = './Dataset/train/noisy/'
clean_dirs_for_train = './Dataset/train/clean/'
noisy_dirs_for_valid = './Dataset/valid/noisy/'
clean_dirs_for_valid = './Dataset/valid/clean/'

max_epoch = 30
batch = 4
learning_rate = 0.001
joint_loss = True

DEVICE = 'cpu'

model_type = ['Baseline', 'Proposed']
model_mode = model_type[1]
