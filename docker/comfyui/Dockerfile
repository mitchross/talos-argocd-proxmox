# Base image with Python 3.11 and CUDA 12.5 support
FROM nvidia/cuda:12.5.0-runtime-ubuntu22.04

RUN apt-get update

# Satisfy tzdata whingeing from APT
ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
RUN apt-get install -y tzdata

# Install a current version of Python
RUN apt-get -y install software-properties-common
RUN add-apt-repository -y ppa:deadsnakes/ppa
RUN apt-get update
RUN apt-get install -y python3.11
RUN apt-get install -y python3.11-dev

# And make sure it's the one we want
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 10
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1
RUN update-alternatives --auto python3

# PIP
RUN apt-get install -y python3-pip
RUN pip3 install --upgrade pip

# GIT
RUN apt-get install -y git

# Now, start installing ComfyUI
WORKDIR /usr/local
RUN git clone https://github.com/comfyanonymous/ComfyUI.git

# Some custom nodes that I find useful
WORKDIR /usr/local/ComfyUI/custom_nodes
RUN git clone https://github.com/Extraltodeus/ComfyUI-AutomaticCFG
RUN git clone https://github.com/Clybius/ComfyUI-Extra-samplers
RUN git clone https://github.com/flowtyone/ComfyUI-Flowty-LDSR.git
RUN git clone https://github.com/ltdrdata/ComfyUI-Manager
RUN git clone https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes.git
RUN git clone https://github.com/city96/ComfyUI_ExtraModels
RUN git clone https://github.com/ssitu/ComfyUI_UltimateSDUpscale --recursive

# Install all the package dependencies
WORKDIR /usr/local/ComfyUI
RUN pip3 install --default-timeout=1000 --no-cache-dir torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu122
RUN find . -name requirements.txt -exec pip3 --no-input install --default-timeout=1000 --no-cache-dir -r {} \;

# Create startup script directly in the image
RUN echo '#!/bin/sh\ncd /usr/local/ComfyUI\n/usr/bin/python3 main.py $*' > /usr/local/bin/comfyui && \
    chmod +x /usr/local/bin/comfyui

# Make sure we expose the port
EXPOSE 8188

ENTRYPOINT [ "/usr/local/bin/comfyui" ]