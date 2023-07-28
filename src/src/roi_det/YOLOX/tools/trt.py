#!/usr/bin/env python3
# -*- coding:utf-8 -*-
# Copyright (c) Megvii, Inc. and its affiliates.

import argparse
import os
import shutil

import tensorrt as trt
import torch
from loguru import logger
from torch2trt import torch2trt
from yolox.exp import get_exp


def make_parser():
    parser = argparse.ArgumentParser("YOLOX ncnn deploy")
    parser.add_argument("-expn", "--experiment-name", type=str, default=None)
    parser.add_argument("-n",
                        "--name",
                        type=str,
                        default=None,
                        help="model name")
    parser.add_argument("-s", "--save-path", type=str, default=None)

    parser.add_argument(
        "-f",
        "--exp_file",
        default=None,
        type=str,
        help="please input your experiment description file",
    )
    parser.add_argument("-c",
                        "--ckpt",
                        default=None,
                        type=str,
                        help="ckpt path")
    parser.add_argument("-w",
                        '--workspace',
                        type=int,
                        default=32,
                        help='max workspace size in detect')
    parser.add_argument("-b",
                        '--batch',
                        type=int,
                        default=1,
                        help='max batch size in detect')
    return parser


@logger.catch
@torch.no_grad()
def main():
    args = make_parser().parse_args()
    exp = get_exp(args.exp_file, args.name)
    if not args.experiment_name:
        args.experiment_name = exp.exp_name

    model = exp.get_model()
    save_dir = os.path.join(exp.output_dir, args.experiment_name)
    os.makedirs(save_dir, exist_ok=True)
    if args.ckpt is None:
        ckpt_file = os.path.join(save_dir, "best_ckpt.pth")
    else:
        ckpt_file = args.ckpt

    print(f'Loading torch model from {ckpt_file}')
    print(f'Model will be saved in {save_dir} directory')

    ckpt = torch.load(ckpt_file, map_location="cpu")
    # load the model state dict

    model.load_state_dict(ckpt["model"])
    logger.info("loaded checkpoint done.")
    model.eval()
    model.cuda()
    model.head.decode_in_inference = False
    x = torch.ones(1, 3, exp.test_size[0], exp.test_size[1]).cuda()
    model_trt = torch2trt(
        model,
        [x],
        fp16_mode=True,
        log_level=trt.Logger.INFO,
        max_workspace_size=(1 << args.workspace),
        max_batch_size=args.batch,
    )
    logger.info("Converted TensorRT model done. Saving..")
    torch.save(model_trt.state_dict(), os.path.join(save_dir, "model_trt.pth"))
    if args.save_path:
        os.makedirs(os.path.dirname(args.save_path), exist_ok=True)
        torch.save(model_trt.state_dict(), args.save_path)
    engine_file = os.path.join(save_dir, "model_trt.engine")
    with open(engine_file, "wb") as f:
        f.write(model_trt.engine.serialize())
    logger.info(
        "Converted TensorRT model engine file is saved for C++ inference.")


if __name__ == "__main__":
    main()