import os
import time
import torch
from Baseline import Baseline
from Proposed import Proposed
from trainer import train, valid, joint_train, joint_valid
from dataloader import create_dataloader
import tools
import config as cfg
import warnings

warnings.filterwarnings("ignore")

dir2sav = cfg.job_dir
dir2log = cfg.logs_dir

# make the folder
if not os.path.exists(dir2sav):
    os.mkdir(dir2sav)
if not os.path.exists(dir2log):
    os.mkdir(dir2log)

# device setup
DEVICE = torch.device(cfg.DEVICE)

# define model
if cfg.model_mode == 'Baseline':
    model = Baseline().to(DEVICE)
elif cfg.model_mode == 'Proposed':
    model = Proposed().to(DEVICE)

# define train mode
if cfg.joint_loss:
    trainer = joint_train
    validator = joint_valid
else:
    trainer = train
    validator = valid

optimizer = torch.optim.Adam(model.parameters(), lr=cfg.learning_rate)
total_params = tools.cal_total_params(model)

# load the params if there is pretrained model
epoch_start_idx = 1
if os.path.exists(cfg.pretrained_addr):
    print('Load the pretrained model...')
    chkpt = torch.load(cfg.pretrained_addr +
                       '/chkpt_{}.pt'.format(cfg.chkpt_num))
    model.load_state_dict(chkpt['model'])
    optimizer.load_state_dict(chkpt['optimizer'])
    epoch_start_idx = chkpt['epoch'] + 1

    dir2sav = cfg.pretrained_addr

# create dataloader
train_loader = create_dataloader(mode='train')
valid_loader = create_dataloader(mode='valid')

# print model info
print('%d-%d-%d %d:%d:%d\n' %
      (time.localtime().tm_year, time.localtime().tm_mon,
       time.localtime().tm_mday, time.localtime().tm_hour,
       time.localtime().tm_min, time.localtime().tm_sec))
print('total params   : %d (%.2f M, %.2f MBytes)\n' %
      (total_params,
       total_params / 1000000.0,
       total_params * 4.0 / 1000000.0))

# save the status information
tools.write_status(dir2sav)

# save model info
writer = tools.Writer(dir2log)
train_log_fp = open(dir2sav + '/train_log.txt', 'a')

print('Main program start...')
for epoch in range(epoch_start_idx, cfg.max_epoch + 1):
    st_time = time.time()

    # train
    train_loss = trainer(model, train_loader, optimizer, writer, epoch, DEVICE)

    # validate
    valid_loss, pesq, stoi = validator(
        model, valid_loader, writer, epoch, DEVICE)
    print('EPOCH[{}]\n').format(epoch)
    print('PESQ {:.6f} | STOI {:.6f}'.format(pesq, stoi))
    # write train log
    train_log_fp.write('EPOCH[{}]\n').format(epoch)
    train_log_fp.write('PESQ {:.6f} | STOI {:.6f}\n'.format(pesq, stoi))

print('Training has finished.')
train_log_fp.close()
