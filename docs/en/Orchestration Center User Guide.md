<!--
Copyright (c) 2026 Huawei Technologies Co., Ltd.
All Rights Reserved.

SPDX-License-Identifier: Apache-2.0

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
# Orchestration Center User Guide

## 1. Feature Introduction

The Orchestration Center is a visual orchestration platform for multi-agent collaboration. It supports defining invocation relationships and execution flows between Agents through a graphical workflow designer. The backend uses a Python framework to parse workflows and drive Agent collaboration, helping users efficiently build, manage, and run complex Agent collaboration workflows.

### 1.1 Application Scenarios

- **Multi-Agent Collaboration Orchestration**: When business requires multiple agents to collaborate on complex tasks, define invocation relationships and execution order visually.
- **Workflow Template Management**: Save commonly used collaboration workflows as templates for reuse and sharing.
- **Intelligent Workflow Generation**: Automatically generate workflow plans based on natural language descriptions or PDF documents, lowering the barrier to orchestration.
- **Real-Time Process Monitoring**: Execute workflows in streaming mode and push runtime progress in real time for debugging and monitoring.

### 1.2 Capability Scope

The following REST API endpoints are exposed externally:

- **SOP Orchestration API**: Generate PSOP workflows based on natural language SOP text or PDF/TXT/MD files.
- **Intent Orchestration API**: Automatically plan and generate executable PSOP workflows based on natural language intent descriptions.
- **Auto Orchestration Execution API**: Automatically retrieve or generate a PSOP based on a task description and execute it, returning SSE streaming execution progress.
- **Specified PSOP Execution API**: Execute a known workflow by PSOP ID, returning SSE streaming execution progress.
- **Agent List Query API**: Retrieve all available Agents in the system and their skill information.
- **Execution Result Query API**: Query the execution result of a workflow by execution ID.

### 1.3 Highlight Features

- **Visual Orchestration**: Provides a graphical workflow designer. Design Agent collaboration workflows by dragging, dropping, and connecting — no coding required.
- **Multi-Mode Generation**: Supports three workflow creation methods: PDF import, manual orchestration, and natural language generation, accommodating different user preferences.
- **Intelligent Retrieval**: Retrieve historical workflows based on natural language intent, enabling quick reuse of existing processes.
- **Real-Time Streaming Execution**: Push execution progress in real time via SSE for frontend display and issue troubleshooting.

### 1.4 Implementation Principles

For the core workflow of the Orchestration Center, see: [OpenAN Quick Start, Section 3.1.4  Core Process Verification](https://github.com/project-openan/docs/blob/main/en/quick_start.md#314-core-flow-verification).

### 1.5 Relationship with Related Features

| Related Feature | Relationship Description |
| --- | --- |
| Registry Center | The Orchestration Center retrieves the AgentCard list from the Registry Center to discover available Agents and their capabilities |

## 2. Starting the Service

### 2.1 Prerequisites

- **Node.js**: 20.19 or later
- **Python**: 3.12 or later (for starting sample Agent services)

### 2.2 Starting the Service

#### 2.2.1 **Start the Registry Center Service**

   All Agent information displayed on the UI is retrieved from the Registry Center. For details, see the [Registry Center User Guide](https://github.com/project-openan/registry-center/blob/main/docs/en/Registry%20Center%20User%20Guide.md).

#### 2.2.2 **Start the Orchestration Center Backend Service**

Method 1: Install the Service Using a Script (Linux)

The Orchestration Center provides the `install_service.sh` script, which supports installing the Orchestration Center as a systemd service for easy service management and automatic startup on boot.

1. Configure Deployment Parameters (Optional)

The script's default configuration file is located at `etc/systemd/deploy.conf`. The following parameters can be modified as needed:

| Parameter Name | Default Value | Description |
| --- | --- | --- |
| INSTALL_DIR | /OpenA2A-T/orchestration-center | Service installation directory |
| PYTHON_PATH | {INSTALL_DIR}/venv/bin/python3 | Python interpreter path |
| SERVICE_NAME | orchestration-center | systemd service name |
| INSTALL_DEPS | true | Whether to automatically install dependencies |

2. Create a Virtual Environment

Enter the project directory, create and activate the virtual environment:
```bash
cd {install_dir}/orchestration-center
python3 -m venv venv
source venv/bin/activate
```

3. Install the Service

Use the script to install the service (root privileges required):
```bash
cd {install_dir}/orchestration-center/bin
sudo ./install_service.sh install
```

Supported script commands:

| Command | Description |
| --- | --- |
| install | Install the systemd service |
| uninstall | Remove the systemd service |
| status | View service status |
| start | Start the service |
| stop | Stop the service |
| restart | Restart the service |
| enable | Enable automatic startup on boot |
| disable | Disable automatic startup on boot |

Optional parameters:
- `--dir=PATH`: Specify the installation directory
- `--python=PATH`: Specify the Python interpreter path
- `--no-deps`: Skip dependency installation

Example:
```bash
# Specify installation directory and Python path
sudo ./install_service.sh install --dir=/opt/my-orchestration --python=/usr/bin/python3

# Skip dependency installation (use when dependencies are already manually installed)
sudo ./install_service.sh install --no-deps
```

4. Start the Service

After installation is complete, use the following command to start the service:
```bash
sudo ./install_service.sh start
```

Or use the systemctl command:
```bash
sudo systemctl start orchestration-center
```

5. Check Service Status

```bash
sudo ./install_service.sh status
```

Or:
```bash
sudo systemctl status orchestration-center
```

6. View Startup Logs

```bash
journalctl -u orchestration-center -f
```

If you see `Uvicorn running on http://127.0.0.1:5001`, the startup is successful.

Method 2: Manual Startup (Windows)

1. Create a Virtual Environment

Open a cmd window, enter the project directory, and run:
```bash
python -m venv .venv
```

To specify a Python version:
```bash
{actual_python_install_path}/python.exe -m venv .venv
```

2. Activate the Virtual Environment
```powershell
.\.venv\Scripts\Activate.ps1
```

3. Install Project Dependencies
```bash
pip install -r .\requirements.txt
```

4. Start the Project
```bash
python -m orchestrate.start
```

Method 3: Manual Startup (Linux, non-systemd)

1. Create a Virtual Environment
```bash
python3 -m venv myproject_env
source myproject_env/bin/activate
```

2. Install Project Dependencies
```bash
pip install -r ./requirements.txt
```

3. Start the Project
```bash
nohup python -m orchestrate.start > orchestrate.log 2>&1 &
```

4. View Startup Logs
```bash
tail -f orchestrate.log
```

#### 2.2.3 **Install Frontend Dependencies and Start**

   Enter the `workflow-designer` directory under the installation directory:
   ```bash
   cd {install_dir}/workflow-designer
   npm install --force
   npm run dev
   ```
#### 2.2.4 **(Optional) Start Sample Agent Service**

   To view the full demo, start the sample Agent service (the Registry Center has no registered Agents by default; this script registers multiple Agents with the Registry Center and starts the corresponding services):

   ```bash
   cd {install_dir}
   python -m samples.start_agents_server
   ```
#### 2.2.5 **(Optional) Use the One-Click Start Script**

   Enter the `bin` folder under the project directory and run the script (this script automatically starts the frontend service and the sample Agent service):

   ```bash
cd {install_dir}/bin
   ./start_samples.sh
   ```
## 2.5 Security Configuration

The Orchestration Center supports multiple security configurations depending on your deployment scenario. Choose the appropriate level based on your environment.

### Development Mode (No Security)

For local development and testing, all security features can be disabled:

```ini
# etc/conf/server.conf
enable_https=false
verify_client=false
access_password=
persistence_mode=file
```

No login page, no HTTPS, no certificate required. All API endpoints are open.

### Production Mode (HTTPS + Login)

For deployment behind Nginx (recommended):

1. **Configure Nginx with a CA-signed certificate** (from Let's Encrypt, Alibaba Cloud SSL, or your enterprise CA).
2. **Enable login authentication** on the backend:

   ```ini
   # etc/conf/server.conf
   enable_https=true          # Backend uses HTTPS (optional if behind Nginx)
   verify_client=false         # No mTLS required for browser access
   access_password=<sha256_hash>  # Set to enable login
   persistence_mode=postgresql   # Use database for user management
   ```

   Generate the password hash:
   ```bash
   python generate_access_password.py
   ```

3. **Users and registration**: When `persistence_mode=postgresql`, the system automatically creates a default `admin` user (password: `OpenAN@2026`) on first startup. New users can self-register via the registration link on the login page. In `file` mode, registration is not available and only the `access_password` config is used.

### High-Security Mode (mTLS + HTTPS + Login)

For distributed deployments where services communicate over untrusted networks:

```ini
# etc/conf/server.conf
enable_https=true
verify_client=true            # Require client certificates for inbound connections
client_verify_server=true      # Verify remote server certificates for outbound connections
access_password=<sha256_hash>
persistence_mode=postgresql
```

All services must present valid certificates signed by a trusted CA during TLS handshake. See the [Certificate Generation Guide](#) for cross-team certificate setup.

### Security Configuration Summary

| Config | Development | Production (Nginx) | High Security (Distributed) |
|--------|------------|-------------------|---------------------------|
| `enable_https` | false | true | true |
| `verify_client` | false | false | true |
| `client_verify_server` | false | false | true |
| `access_password` | empty | SHA-256 hash | SHA-256 hash |
| `persistence_mode` | file | postgresql | postgresql |
| Registration | N/A | Enabled | Enabled |
| Frontend | HTTP | HTTPS (via Nginx) | HTTPS (via Nginx) |
| Nginx cert | N/A | CA-signed | CA-signed |

### Generating Self-Signed Certificates

For development or internal testing:

```bash
python -m generate_selfsign_cert etc/ssl serverAuth
```

New TLS certificates include SANs for `DNS:localhost`, `IP:127.0.0.1` and `IP:::1` by default.
For other endpoints, repeat `--dns` / `--ip` for the actual client-facing names; explicit options replace the default SAN list:

```bash
python -m generate_selfsign_cert etc/ssl-new serverAuth --dns orch.example.test --ip 192.0.2.10
```

SANs must match the host in the client URL; IP addresses require `--ip`. Setting CN or trusting a certificate does not fix missing SANs.
Existing certificates are not updated automatically, and the tool refuses to overwrite certificates or private keys.
For an existing deployment, generate into a new directory, back up and deploy the matching certificate/key pair, then restart.
Update client trust material where required; do not overwrite the CA store used to authenticate clients.
`dataSigning` does not add TLS SANs and rejects CLI SAN options.

This generates RSA 3072-bit certificates that comply with the built-in certificate validator. Copy the generated files to the expected names:

```bash
cd etc/ssl
cp server_RSA.cer server.cer
cp server_key_RSA.pem server_key.pem
cp server.cer trust.cer
echo -n "<password>" > cert_pwd
```

For production, use certificates from a trusted CA (Let's Encrypt, Alibaba Cloud SSL, or enterprise CA).


## 3. Usage

### 3.1 Prerequisites

- The Registry Center service is started and running normally
- The Orchestration Center backend service is started and running normally
- The Orchestration Center frontend service has been successfully started
- The browser can normally access the Orchestration Center frontend page

### 3.2 Background Information

The Orchestration Center provides three workflow creation methods:

- **PDF Import**: Parse workflow descriptions from PDF documents to automatically generate a workflow
- **Manual Orchestration**: Visually define workflows by dragging Agent cards onto the canvas and connecting them
- **Natural Language Generation**: Input a business intent description, and the backend automatically generates the corresponding workflow

When executing a workflow, the system pushes execution progress in real time via SSE (Server-Sent Events), allowing the frontend to display each Agent's request and response in real time.

### 3.3 Usage Limitations

- The current version only supports parsing sections titled "5. Interaction Flow" in PDF documents
- Workflow IDs are automatically generated upon saving and do not support customization
- Agents started by the sample script are for demo purposes only; production environments should connect to real Agent services

### 3.4 Operation Steps

1. **Access the Orchestration Center Interface**

   Open a browser and navigate to the frontend URL (e.g., `http://localhost:3003` for development, or `https://your-domain.com` for production).

2. **Login (if authentication is enabled)**

   If `access_password` is configured or `persistence_mode=postgresql`, the login page is displayed. Enter your username and password to access the main interface.

   - Default admin credentials: username `admin`, password `OpenAN@2026` (in PostgreSQL mode, the admin user is auto-created on first startup).
   - To register a new account (PostgreSQL mode only), click the registration link on the login page.
   - In `file` mode, the username is `admin` and the password is the value set in `access_password` (before hashing).
   - To change the admin password in file mode, regenerate the hash: `python generate_access_password.py`

3. **Configure the Service Address (Optional)**

   If the backend is not accessible at the default address, click the gear icon in the lower-right corner of the login page (or the upper-right corner on the main interface) to configure the backend IP, port, and connection mode (Direct IP or Nginx Gateway).

3. **View the Agent Library**

   The left panel displays the full list of Agents. You can search and filter by Agent name or capability keywords. Click any Agent to view its detailed information in the right panel.

4. **Create a New Workflow**

   - Click the `+` button at the top of the left panel
   - Select a creation method:

     | Method | Operation Description |
     | --- | --- |
     | PDF Import | Upload a PDF file; the system automatically parses and generates a PSOP |
     | Manual Orchestration | Drag Agent cards from below onto the canvas and define the execution order by connecting them; click a connection to set jump conditions |
     | Natural Language Generation | Input a business intent description; the backend automatically orchestrates and generates a PSOP |

    **PDF Import:**

    Click the "SolutionPackage Import" option, select a PDF document to upload, and wait for the upload to complete.
    After uploading, users can edit before saving.

    **Note:** Only SolutionPackage-type PDF files are supported for import. A SolutionPackage is a standard solution package document format defined by TM Forum for describing solutions and interaction flows in the telecommunications industry. Refer to the [TM Forum website](https://www.tmforum.org/search?contentType=Asset&pageIndex=1&searchTerm=an%20l4%20solution%20package) for relevant standard documents and examples.

   **Manual Orchestration:**
    - Step 1: Add Agent cards:
     Drag the desired Agent cards from the area below the interface onto the blank canvas area.
    - Step 2: Configure Agent skills:
     Click an added Agent card on the canvas, and select the skill item to use from the pop-up options.
    - Step 3: Add more Agents:
     Repeat steps 1 and 2 to drag multiple Agents onto the canvas based on business requirements.
    - Step 4: Connect Agent cards:
     Hover the mouse over the "small blue dot" on the right side of an Agent card; the cursor will change to a crosshair. Hold down the left mouse button, drag to another Agent card, and release to complete the connection.
    - Step 5: Configure branch conditions:
     Click a connection that needs branch configuration, enter the jump condition in the "Branch Configuration" prompt box in the pop-up window, and save. Subsequent execution will follow different branch paths based on different conditions.
    - Step 6: Save the workflow:
     After all configuration is complete, click the "Save" button at the top of the canvas to create or update the workflow.

    **Natural Language Generation:**

    Click the "Natural Language Orchestration" option, enter a natural language description in the pop-up input box, and click the "GENERATE" button.
    The generated PSOP workflow will be displayed in the current window. It is in "Edit" state by default and can be saved directly or modified before saving.

5. **Save the Workflow**

   After completing orchestration, the system either auto-saves or manually triggers a save operation. The returned `workflow_id` can be used for subsequent retrieval and execution.

6. **View Existing Workflows**

   All PSOPs are displayed in the left panel. Use the search box at the top to quickly find them by name. Click any PSOP to view its detailed information in the right panel.

7. **Execute a Workflow**
- Enter the user intent in the top input box;
- Click the "Retrieve Workflow" button on the right;
- Once the system retrieves the corresponding PSOP, the left panel will display that PSOP;
- The center area will automatically display the workflow for that PSOP;
- Click the "▶" button to the right of the PSOP in the left panel; the right side of the page will display the workflow execution process in real time.

## 4. FAQ

### 4.1 Why is the Agent library empty on the left after startup?

**Symptom**: After entering the Orchestration Center interface, no Agents are displayed in the left Agent library.

**Possible Causes**:

- The Registry Center service is not started
- The Orchestration Center backend service is not correctly configured with the Registry Center address
- The sample Agent service is not started (demo environment)

**Solutions**:

1. Confirm that the Registry Center service has been started normally
2. Check that the Registry Center address in the Orchestration Center backend configuration file is correct
3. To view the demo, run `python -m samples.start_agents_server` to start the sample Agent
