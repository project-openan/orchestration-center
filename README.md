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

## 启动和停止服务
1. **启动后端服务**

    **进入项目目录下的`bin`文件夹**
    ```bash
      cd /yourPath/orchestration-center/bin
    ``` 
   **创建并激活虚拟环境**

    先创建一个项目所需的虚拟环境，比如使用`conda` 创建一个名为`orchestration-center`的虚拟环境(如果尚未创建)：
   ```bash
      conda create -n orchestration-center 
    ```
    激活虚拟环境
    ```bash
      conda activate orchestration-center 
    ```
   安装项目所需的python依赖(如果未安装)：
    ```bash
      pip install -r ../requirements.txt
    ```
   方式一：

   执行启动脚本以运行项目：
    ```bash
      ./start.sh
    ```
   方式二：
   ```bash
      python -m orchestrate.start
    ```
2. **停止后端服务**

   **进入项目目录下的`bin`文件夹**
    ```bash
      cd /yourPath/orchestration-center/bin
    ``` 
   执行脚本文件：
    ```bash
      ./stop.sh
    ```
### 启动和停止Samples
1. **启动Samples**
   
   方式一:

   **进入项目目录下的`bin`文件夹**
    ```bash
      cd /yourPath/orchestration-center/bin
    ``` 
   执行脚本文件：
    ```bash
      ./start_samples.sh
    ```
   方式二：
   ```bash
      python -m samples.start_agents_server
    ```
2. **停止Samples**

   **进入项目目录下的`bin`文件夹**
    ```bash
      cd /yourPath/orchestration-center/bin
    ``` 
   执行脚本文件：
    ```bash
      ./stop_samples.sh
    ```

### 访问应用
1. 打开浏览器访问 http://localhost:3003
2. 使用工作流设计器创建和编辑流程图
3. 通过 API 接口管理 PSOP 工作流

## API 文档

详细的 API 文档请参考 `framework/server/PSOP_API_DOCUMENTATION.md`，包含以下主要接口：

- `GET /psops` - 获取 PSOP 列表
- `GET /psops/{workflow_id}` - 获取 PSOP 详情
- `POST /psops` - 保存 PSOP
- `DELETE /psops/<workflow_id>` - 删除PSOP
- `POST /parse-pdf` - 解析 PDF 文件
- `POST /plan` - 获取工作流规划
- `GET /agent-cards` - 获取全量AgentCard列表
- `POST /generate-from-intent` - 根据自然语言意图生成PSOP
- `POST /retrieve-by-intent` - 根据自然语言意图检索PSOP
- `GET /rest/start_process_stream?psop_id=<id>` - 启动PSOP执行并推送实时进展