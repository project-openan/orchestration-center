<!--
!/usr/bin/env python3
Copyright (c) 2026 Huawei Technologies Co., Ltd.
All Rights Reserved.

   Licensed under the Apache License, Version 2.0 (the "License"); you may
   not use this file except in compliance with the License. You may obtain
   a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
   License for the specific language governing permissions and limitations
   under the License.
-->


# A2A-T 多智能体编排中心

## 项目简介

编排中心是一个用于编排多个 Agent（智能体）协作的 Web 平台。用户在可视化工作流设计器中编排 Agent 之间的调用关系和流程图，后端 Python 框架负责解析流程、执行编排逻辑并驱动 Agent 协同工作。

## 快速开始

### 环境要求
- Node.js 20.19
- Python 3.10+

## 启动前配置
### ip端口配置(可选)
本项目默认是在回环地址127.0.0.1：60000上开放端口侦听，接受restful请求，可按照实际需要，修改此ip、端口配置。
配置文件：{安装目录}/etc/conf/server.conf
默认配置如下，可按需修改：
ip=127.0.0.1
port=60000
### 证书配置
目标系统需提供一套完整证书用于启动端口，后续接受REST请求时会建立TLS传输通道，并根据配置校验对端证书。
配置文件：{安装目录}/etc/conf/server.conf
默认配置如下，可按需修改：

ssl_certfile=etc/ssl/server.cer

ssl_keyfile=etc/ssl/server_key.pem

ssl_keyfile_password=etc/ssl/cert_pwd

ssl_ca_certs=etc/ssl/trust.cer

verify_client=true

enable_https=true
如果沒有证书或者不想校验证书，将enable_https字段设置为false即可

persistence_mode=postgresql

数据的保存目前有两种：postgresql和file，如果设置为postgresql，则需要修改{安装目录}/etc/conf/db_config.json中的配置为你当前环境的postgresql的配置，如果只是想简单使用，不想使用数据库保存数据，只需要将该字段修改为file即可，数据会保存在本地{安装目录}/data目录下。

证书要求：
server.cer：必选，身份证书，仅支持pem编码格式
证书格式：X.509v3
证书秘钥算法、秘钥长度：RSA(>= 3072 bits)，ECDSA(>= 256 bits)
有效期：当前时间有效

cert_pwd:必选，私钥口令，文件名固定无后缀
内容要求为密文
口令原始明文复杂度需满足要求：至少8个字符，至少包含两种字符(数字、大写字母、小写字母、特殊字符`~!@#$%^&*()-_=+ | [{}]);:'",<.>/?和空格
口令原始明文需与server_key.pem匹配

server_key.pem:必选，私钥文件，金支持pem编码格式
私钥与公钥的匹配性：需要与server.cer中的公钥时匹配的

trust.cer:默认必选，仅支持pem编码格式，仅支持.cer文件，文件名固定，如果涉及多本证书，需合成一本
启动配置项ssl_verify_client=true时，必须存在
校验证书格式：X.509v3
校验有效期：当前时间有效
秘钥算法、长度：RSA(>= 3072 bits)，ECDSA(>= 256 bits)

revocationlist.crl:可选，吊销列表，仅支持pem编码格式，仅支持.crl文件，文件名固定，如果涉及多本证书，需合成一本，可以不存在
校验证书格式：X.509v2
校验有效期：当前时间有效
不支持国密证书

注意：
1.证书校验失败，将导致进程拉起失败。
2.证书文件权限要求：客户配置修改证书路径后，需保证证书文件及所在目录的权限最小化(例如文件权限400，目录权限700)，同时需确保本项目进程拥有对文件的读取权限
3.证书变更后，需重启进程生效

本项目仅读取使用这些证书，不提供证书管理能力，例如证书过期告警、备份恢复等。

## 启动编排中心服务
### windows启动方式
#### 1. 创建虚拟环境
下载本项目代码后，使用pycharm打开，在pycharm中创建一个虚拟环境
![photo](docs/images/create_virtual_environment.png)

点击`Add new Interpreter`, 再点击`Add Local Interpreter...`
![photo](docs/images/create_virtual_environment_1.png)
   
选择python版本和路径，点击`ok`即可

#### 2. 安装项目依赖
等待虚拟环境创建好之后，打开pycharm的终端窗口，执行如下命令：
```bash
pip install -r .\requirements.txt
```
#### 3. 启动项目
等待依赖下载完成后，在终端窗口执行如下命令即可启动编排中心后端服务：
```bash
python -m orchestrate.start
```
或者打开{安装目录}/orchestrate/start.py文件，右键`Run start`即可。
#### 4.查看是否启动成功
如下图，表示启动成功，如果没有看到该提示，则按照报错信息提示修改后重新尝试启动。
![photo](docs/images/run_success.png)

### linux启动方式
#### 1. 创建虚拟环境
进入到项目所在目录，使用如下命令创建并激活虚拟环境：
```bash
# 创建虚拟环境
python3 -m venv myproject_env

# 激活虚拟环境
source myproject_env/bin/activate
```
#### 2. 安装项目依赖
执行如下命令进行项目依赖的安装：
```bash
pip install -r ./requirements.txt
```
#### 3. 启动项目
执行如下命令即可启动编排中心后端服务，`nohup`的作用是在用户退出登录或关闭终端后继续运行：
```bash
nohup python -m orchestrate.start > orchestrate.log 2>&1 &
```
#### 4.查看是否启动成功
使用如下命令查看启动日志：
```bash
tail -f orchestrate.log
```
如果可以看到`Uvicorn running on http://127.0.0.1:60000`则表示启动成功，如果没有看到该提示，则按照报错信息提示修改后重新尝试启动。
