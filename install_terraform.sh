#!/bin/bash

case "$OSTYPE" in
    darwin*) FILENAME="darwin_amd64" ;;
    *)       FILENAME="linux_amd64" ;;
esac

mkdir tmp
cd tmp
wget https://releases.hashicorp.com/terraform/1.0.1/terraform_1.0.1_${FILENAME}.zip tmp/
unzip ./terraform_1.0.1_linux_amd64.zip
sudo cp terraform /usr/bin
cd ..
rm -rf ./tmp
