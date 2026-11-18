// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0
//
//    Licensed under the Apache License, Version 2.0 (the "License"); you may
//    not use this file except in compliance with the License. You may obtain
//    a copy of the License at
//
//         http://www.apache.org/licenses/LICENSE-2.0
//
//    Unless required by applicable law or agreed to in writing, software
//    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
//    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
//    License for the specific language governing permissions and limitations
//    under the License.
import {useState} from "react";
import {defaultIp, defaultPort, defaultGateway} from "@/service/api.js";
import {Server, X, Globe, Terminal, Save, Link2, LayoutGrid, Network} from "lucide-react";
import {getInitialServerConfig} from './config.js';

const SettingsModal = ({isOpen, onClose, t}) => {
    const [config, setConfig] = useState(() => getInitialServerConfig());

    const handleSave = () => {
        const nextConfig = config.mode === 'nginx'
            ? {mode: 'nginx', nginxUrl: config.nginxUrl || defaultGateway}
            : {mode: 'ip', ip: config.ip || defaultIp, port: config.port || defaultPort};
        localStorage.setItem('server_config', JSON.stringify(nextConfig));
        onClose();
        window.location.reload();
    }

    if (!isOpen) return null;

    return (
        <div
            className={"fixed inset-0 z-[100] flex items-center justify-center p-4 bg-[#112742]/32 backdrop-blur-sm animate-in fade-in duration-300"}>
            <div
                className={"bg-white dark:bg-zinc-900 w-full max-w-md rounded-3xl shadow-modal border border-zinc-100 dark:border-zinc-800 overflow-hidden"}>
                <div className={"p-6 border-b border-zinc-50 dark:border-zinc-800 flex justify-between items-center"}>
                    <div className={"flex items-center gap-3"}>
                        <div className={"p-2 bg-cm-primary rounded-[7px] text-white"}>
                            <Server size={20}/>
                        </div>
                        <h2 className={"text-[16px] font-bold dark:text-white"}>{t('settings.title')}</h2>
                    </div>
                    <button className={"p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-full transition-colors"}
                            onClick={onClose}>
                        <X size={20} className={"text-zinc-400"}/>
                    </button>
                </div>

                <div className={"p-8 space-y-6"}>
                    {/* Mode Selector */}
                    <div className={"space-y-2"}>
                        <label className={"text-[11px] font-semibold text-cm-muted ml-1"}>{t('settings.connection_mode')}</label>
                        <div className={"grid grid-cols-2 gap-2 p-1 bg-zinc-50 dark:bg-zinc-800/50 rounded-2xl border border-zinc-100 dark:border-zinc-700"}>
                            <button
                                onClick={() => setConfig({...config, mode: 'ip', ip: config.ip || defaultIp, port: config.port || defaultPort})}
                                className={`flex items-center justify-center gap-2 py-2 rounded-xl text-xs font-bold transition-all ${config.mode === 'ip' ? 'bg-white dark:bg-zinc-700 shadow-sm text-blue-600 dark:text-blue-400' : 'text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300'}`}
                            >
                                <LayoutGrid size={14}/> {t('settings.direct_ip')}
                            </button>
                            <button
                                onClick={() => setConfig({...config, mode: 'nginx', nginxUrl: config.nginxUrl || defaultGateway})}
                                className={`flex items-center justify-center gap-2 py-2 rounded-xl text-xs font-bold transition-all ${config.mode === 'nginx' ? 'bg-white dark:bg-zinc-700 shadow-sm text-blue-600 dark:text-blue-400' : 'text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300'}`}
                            >
                                <Network size={14}/> {t('settings.nginx_gateway')}
                            </button>
                        </div>
                    </div>

                    {config.mode === 'ip' ? (
                        <>
                            <div className={"space-y-2"}>
                                <label className={"text-[11px] font-semibold text-cm-muted ml-1"}>{t('settings.backend_host')}</label>
                                <div className={"relative"}>
                                    <input type={"text"} value={config.ip}
                                           onChange={(e) => setConfig({...config, ip: e.target.value})}
                                           className={"w-full pl-10 pr-4 py-3 bg-zinc-50 dark:bg-zinc-800 border border-zinc-100 dark:border-zinc-700 rounded-xl font-bold focus:ring-4 focus:ring-blue-500/10 outline-none transition-all dark:text-white"}
                                           placeholder={"127.0.0.1"}/>
                                    <Globe size={16} className={"absolute left-3.5 top-3.5 text-zinc-400"}/>
                                </div>
                            </div>

                            <div className={"space-y-2"}>
                                <label className={"text-[11px] font-semibold text-cm-muted ml-1"}>{t('settings.port')}</label>
                                <div className={"relative"}>
                                    <input type={"text"} value={config.port}
                                           onChange={(e) => setConfig({...config, port: e.target.value})}
                                           className={"w-full pl-10 pr-4 py-3 bg-zinc-50 dark:bg-zinc-800 border border-zinc-100 dark:border-zinc-700 rounded-xl font-bold focus:ring-4 focus:ring-blue-500/10 outline-none transition-all dark:text-white"}
                                           placeholder={defaultPort}/>
                                    <Terminal size={16} className={"absolute left-3.5 top-3.5 text-zinc-400"}/>
                                </div>
                            </div>
                        </>
                    ) : (
                        <div className={"space-y-2"}>
                            <label className={"text-[11px] font-semibold text-cm-muted ml-1"}>{t('settings.gateway_base_url')}</label>
                            <div className={"relative"}>
                                <input type={"text"} value={config.nginxUrl}
                                       onChange={(e) => setConfig({...config, nginxUrl: e.target.value})}
                                       className={"w-full pl-10 pr-4 py-3 bg-zinc-50 dark:bg-zinc-800 border border-zinc-100 dark:border-zinc-700 rounded-xl font-bold focus:ring-4 focus:ring-blue-500/10 outline-none transition-all dark:text-white"}
                                       placeholder={defaultGateway}/>
                                <Link2 size={16} className={"absolute left-3.5 top-3.5 text-zinc-400"}/>
                            </div>
                            <p className={"text-[10px] text-zinc-400 italic px-1"}>{t('settings.gateway_example', {url: 'http://192.168.1.100/orchestration'})}</p>
                        </div>
                    )}

                    <p className={"text-[11px] text-zinc-400 font-medium italic leading-relaxed"}>
                        {t('settings.reload_note')}
                    </p>
                </div>

                <div
                    className={"p-6 bg-zinc-50/50 dark:bg-zinc-900/50 border-t border-zinc-50 dark:border-zinc-800 flex gap-3"}>
                    <button onClick={onClose}
                            className={"cm-btn flex-1 min-h-[39px] text-[13px] text-cm-muted"}
                    >
                        {t('common.cancel')}
                    </button>
                    <button onClick={handleSave}
                            className={"cm-btn-primary flex-1 min-h-[39px] text-[13px]"}
                    >
                        <Save size={16}/> {t('settings.save_config')}
                    </button>
                </div>
            </div>
        </div>
    )
}
export default SettingsModal;
