import torch
import numpy as np
import random

from data.dataset import MotionDataset
from model.rtn import RTN
from vis.vis import display_with_keys

# RTN parameters
total_frames = 300
past_context = 10
target_frames = [30, 60, 90, 120, 150, 180, 210, 240, 270, 299]

# dataset parameters
window_size = 300
offset = 150
target_fps = 30

# dataset
device = "cuda" if torch.cuda.is_available() else "cpu"
test_dset = MotionDataset("D:/data/PFNN", train=False, window=window_size, offset=offset, phase=False, target_fps=target_fps)

def anim(tensor):
    return tensor.detach().cpu().view(tensor.shape[0], -1, 3).numpy()

if __name__ == "__main__":
    seed = 777
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.backends.cudnn.deterministic = True

    # prepare training data
    gv_root = test_dset.extract_features("global_vel_root")
    gp_root = test_dset.extract_features("global_pos_root")
    gp = test_dset.extract_features("global_pos")
    gp_root_rel = gp - gp_root.tile(1, 1, gp.shape[-1] // gp_root.shape[-1])
    test_data = torch.cat([gv_root, gp_root_rel[..., 3:]], dim=-1)

    parents = test_dset.extract_features("parents")
    
    # load model
    model = RTN(test_data.shape[-1]).to(device)
    model.load_state_dict(torch.load("save/rtn.pth")["model"])
    model.eval()
    with torch.no_grad():
        for i in range(test_data.shape[0]):
            idx = random.randint(0, test_data.shape[0] - 1)
            data = test_data[idx:idx+1].to(device)
            mean, std = data.mean(), data.std()
            data = (data - mean) / (std + 1e-8)

            # network initialization
            preds = []

            for t_idx, t_frame in enumerate(target_frames):
                model.init_hidden(1, data[:, 0 if t_idx == 0 else target_frames[t_idx-1], :])
                model.set_target(data[:, t_frame, :])

                if t_idx == 0:
                    for f in range(0, past_context):
                        pred = model(data[:, f, :])
                        preds.append(data[:, f+1, :])
                    for f in range(past_context, t_frame):
                        pred = model(pred)
                        preds.append(pred)
                else:
                    for f in range(-past_context, 0):
                        pred = model(preds[f])
                    for f in range(0, t_frame - target_frames[t_idx-1]):
                        pred = model(pred)
                        preds.append(pred)

            preds = torch.stack(preds, dim=1) * std + mean

            # gt
            gt = data * std + mean

            # make animation to visualize
            pred_rtn = anim(preds[0])
            gt = anim(gt[0])

            ########## ground truth motion ##########
            def get_joint_pos(data):
                start_root_pos = gp_root[idx, 0:1].numpy()
                root_pos_delta = np.cumsum(data[:, 0:1, :] / target_fps, axis=0)
                root_pos = start_root_pos + root_pos_delta

                joint_pos = data[:, 1:]
                anim = np.concatenate([root_pos, joint_pos+root_pos], axis=1)
                return anim

            gt_anim = get_joint_pos(gt)
            rtn_anim = get_joint_pos(pred_rtn)
            key_anim = gt_anim[target_frames]
            
            # correction = gt_anim[-1] - pred_anim[-1]
            # for frame in range(past_context, target_frame):
            #     t = 1 - (target_frame - frame) / (past_context - target_frame)
            #     pred_anim[frame] += t * correction
            
            display_with_keys(rtn_anim, parents, key_anim, target_frames, gt=gt_anim, fps=30, bone_radius=0.3, eye=(0, 50, 125))#, save_gif=True, gif_name="save/RTN.gif")
            message = input("Type 'q' to quit: ")
            if message == "q":
                break