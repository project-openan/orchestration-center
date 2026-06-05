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


# A2A-T Multi-Agent Orchestration Center

## Project Overview

The Orchestration Center is a web platform for orchestrating collaboration among multiple Agents. Users arrange the call relationships and flowcharts between Agents in a visual workflow designer, while the backend Python framework is responsible for parsing the flow, executing the orchestration logic, and driving the Agents to work together.

## Quick Start

### Environment Requirements
- Node.js 20.19
- Python 3.10+

## Pre-Launch Configuration
### IP and Port Configuration (Optional)
By default, this project opens a port listening on the loopback address 127.0.0.1:60000 to accept RESTful requests. You can modify this IP and port configuration as needed.
Configuration file: {install directory}/etc/conf/server.conf
The default configuration is as follows and can be modified as needed:
ip=127.0.0.1
port=60000
### Certificate Configuration
The target system must provide a complete set of certificates to start the port. When subsequently accepting REST requests, a TLS transport channel will be established and the peer certificate will be verified according to the configuration.
Configuration file: {install directory}/etc/conf/server.conf
The default configuration is as follows and can be modified as needed:
ssl_certfile=etc/ssl/server.cer
ssl_keyfile=etc/ssl/server_key.pem
ssl_keyfile_password=etc/ssl/cert_pwd
ssl_ca_certs=etc/ssl/trust.cer
verify_client=true

Certificate requirements:
server.cer: Required, identity certificate, only PEM encoding format is supported
Certificate format: X.509v3
Certificate key algorithm and key length: RSA (>= 3072 bits), ECDSA (>= 256 bits)
Validity period: Must be valid at the current time

cert_pwd: Required, private key password, fixed file name with no extension
Content must be ciphertext
The original plaintext password complexity must meet the following requirements: at least 8 characters, containing at least two character types (digits, uppercase letters, lowercase letters, special characters `~!@#$%^&*()-_=+ | [{}]);:'",<.>/? and spaces)
The original plaintext password must match server_key.pem

server_key.pem: Required, private key file, only PEM encoding format is supported
Matching of private key and public key: Must match the public key in server.cer

trust.cer: Required by default, only PEM encoding format is supported, only .cer files are supported, fixed file name. If multiple certificates are involved, they must be combined into one
Must be present when the startup configuration item ssl_verify_client=true
Verification certificate format: X.509v3
Verification validity period: Must be valid at the current time
Key algorithm and length: RSA (>= 3072 bits), ECDSA (>= 256 bits)

revocationlist.crl: Optional, revocation list, only PEM encoding format is supported, only .crl files are supported, fixed file name. If multiple certificates are involved, they must be combined into one. May be absent
Verification certificate format: X.509v2
Verification validity period: Must be valid at the current time
SM (Chinese national cryptographic) certificates are not supported

Notes:
1. Certificate verification failure will cause the process to fail to start.
2. Certificate file permission requirements: After the customer modifies the certificate path in the configuration, the permissions of the certificate files and their directory must be minimized (for example, file permission 400, directory permission 700). At the same time, ensure that this project's process has read permission for the files.
3. After changing a certificate, the process must be restarted for the change to take effect.

This project only reads and uses these certificates. It does not provide certificate management capabilities such as certificate expiration alerts, backup, or recovery.

## Starting and Stopping the Service
1. **Start the backend service**

    **Enter the `bin` folder in the project directory**
    ```bash
      cd /yourPath/orchestration-center/bin
    ```
   **Create and activate a virtual environment**

    First create a virtual environment required by the project, for example using `conda` to create a virtual environment named `orchestration-center` (if not already created):
   ```bash
      conda create -n orchestration-center
    ```
    Activate the virtual environment
    ```bash
      conda activate orchestration-center
    ```
   Install the Python dependencies required by the project (if not already installed):
    ```bash
      pip install -r ../requirements.txt
    ```
   Option 1:

   Run the startup script to launch the project:
    ```bash
      ./start.sh
    ```
   Option 2:
   ```bash
      python -m orchestrate.start
    ```
2. **Stop the backend service**

   **Enter the `bin` folder in the project directory**
    ```bash
      cd /yourPath/orchestration-center/bin
    ```
   Run the script file:
    ```bash
      ./stop.sh
    ```
### Starting and Stopping Samples
1. **Start Samples**

   Option 1:

   **Enter the `bin` folder in the project directory**
    ```bash
      cd /yourPath/orchestration-center/bin
    ```
   Run the script file:
    ```bash
      ./start_samples.sh
    ```
   Option 2:
   ```bash
      python -m samples.start_agents_server
    ```
2. **Stop Samples**

   **Enter the `bin` folder in the project directory**
    ```bash
      cd /yourPath/orchestration-center/bin
    ```
   Run the script file:
    ```bash
      ./stop_samples.sh
    ```

### Accessing the Application
1. Open a browser and visit http://localhost:3003
2. Use the workflow designer to create and edit flowcharts
3. Manage PSOP workflows through the API interfaces

## API Documentation

For detailed API documentation, please refer to `framework/server/PSOP_API_DOCUMENTATION.md`, which includes the following main interfaces:

- `GET /psops` - Get the list of PSOPs
- `GET /psops/{workflow_id}` - Get PSOP details
- `POST /psops` - Save a PSOP
- `DELETE /psops/<workflow_id>` - Delete a PSOP
- `POST /parse-pdf` - Parse a PDF file
- `POST /plan` - Get a workflow plan
- `GET /agent-cards` - Get the full list of AgentCards
- `POST /generate-from-intent` - Generate a PSOP from a natural language intent
- `POST /retrieve-by-intent` - Retrieve a PSOP by natural language intent
- `GET /rest/start_process_stream?psop_id=<id>` - Start PSOP execution and push real-time progress
