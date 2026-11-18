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
import { useState } from "react";
import { Check, Copy, FileJson } from "lucide-react";
import { useTranslation } from "react-i18next";

const CodeInspector = ({ data, fileName = 'manifest.json', isDark = false }) => {
    const { t } = useTranslation();
    const [copied, setCopied] = useState(false);

    const handleCopy = () => {
        navigator.clipboard.writeText(JSON.stringify(data, null, 2));
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }

    const jsonString = JSON.stringify(data, null, 4);

    return (<div className={`flex h-full flex-col p-4 transition-all duration-300 ${isDark ? 'dark' : ''}`}>
        <div className={`flex-1 rounded-cm border overflow-hidden flex flex-col relative transition-colors duration-300 ${isDark ? 'bg-zinc-950 border-zinc-800 shadow-card' : 'bg-white border-cm-line shadow-card'}`}>
            <div className={`flex items-center justify-between gap-3 px-4 py-2 border-b sticky top-0 z-10 backdrop-blur-md transition-colors ${isDark ? 'bg-zinc-950/90 border-zinc-800' : 'bg-white/95 border-cm-line-soft'}`}>
                <div className="flex items-center gap-2 min-w-0">
                    <FileJson size={13} className={`shrink-0 ${isDark ? 'text-blue-400' : 'text-cm-primary'}`} />
                    <span className={`text-[12px] font-semibold truncate leading-none ${isDark ? 'text-zinc-300' : 'text-cm-secondary'}`}>
                        {fileName}
                    </span>
                </div>

                <button onClick={handleCopy}
                    className={`cm-icon-btn relative shrink-0 transition-all duration-200 active:scale-95 ${isDark
                        ? 'text-zinc-400 hover:bg-zinc-800 hover:text-blue-400'
                        : ''}`}
                    title={copied ? t('common.copied') : t('common.copy_raw_json')}>
                    <div className={`transition-all duration-300 ${copied ? 'scale-0 opacity-0' : 'scale-100 opacity-100'}`}>
                        <Copy size={15} strokeWidth={2} />
                    </div>
                    <div className={`absolute transition-all duration-300 ${copied ? 'scale-100 opacity-100' : 'scale-0 opacity-0'}`}>
                        <Check size={16} strokeWidth={2.5} className={"text-emerald-500"} />
                    </div>
                </button>
            </div>

            <div className={"flex-1 overflow-auto custom-scrollbar px-5 py-4"}>
                <pre className={"font-mono text-[12px] leading-[1.7] selection:bg-cm-primary/20"}>
                    <code className={`whitespace-pre transition-colors duration-0 ${isDark ? 'text-blue-300' : 'text-cm-accent'}`}>
                        {jsonString}
                    </code>
                </pre>
            </div>

            <div className={`px-4 py-1.5 border-t flex justify-end transition-colors ${isDark ? 'bg-zinc-900/40 border-zinc-800' : 'bg-cm-canvas border-cm-line-soft'}`}>
                <span className={`text-[10px] font-medium tracking-wider ${isDark ? 'text-zinc-500' : 'text-cm-faint'}`}>
                    UTF-8 · JSON · {jsonString.length} {t('common.chars')}
                </span>
            </div>
        </div>
    </div>);
};

export default CodeInspector;
