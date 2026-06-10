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
import { useTranslation } from "react-i18next";

const ToolbarLite = ({ onFitView, isDark }) => {
    const { t } = useTranslation();

    const theme = {
        container: isDark
            ? 'bg-zinc-950/90 border-zinc-800 shadow-[0_10px_40px_rgba(0,0,0,0.7)]'
            : 'bg-white/95 border-slate-200 shadow-[0_10px_30px_rgba(0,0,0,0.1)]',
        secondaryBtn: isDark
            ? 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100'
            : 'text-slate-600 hover:bg-slate-100',
    };

    return (
        <div
            className={`flex items-center gap-3 p-2 backdrop-blur-md rounded-2xl border w-max justify-center transition-all duration-300 ${theme.container}`}
        >
            <button
                onClick={onFitView}
                title={t('workflow.toolbar.fitView')}
                className={`flex items-center gap-1 px-4 py-1.5 text-sm font-semibold rounded-xl transition-all active:scale-90 ${theme.secondaryBtn}`}
            >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
                    />
                </svg>
                {t('workflow.toolbar.fitView')}
            </button>
        </div>
    );
};

export default ToolbarLite;