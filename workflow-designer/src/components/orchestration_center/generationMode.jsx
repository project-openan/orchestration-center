// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from 'react-i18next';

export default function GenerationMode({ value, onChange, disabled }) {
    const { t } = useTranslation();
    return <label className="flex items-center gap-2 text-[12px] text-cm-secondary dark:text-zinc-300">
        {t('orchestration.generationMode')}
        <select aria-label={t('orchestration.generationMode')} value={value} disabled={disabled}
            onChange={event => onChange(event.target.value)}
            className="h-[33px] rounded-cm-sm border border-cm-line bg-white px-2.5 text-[12px] font-medium text-cm-ink transition-colors
                hover:border-[#B8CFFC] focus:border-[#9ABDFB] focus:outline-none focus:shadow-[0_0_0_3px_rgba(219,234,255,0.5)]
                disabled:cursor-not-allowed disabled:opacity-60
                dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:hover:border-zinc-600">
            <option value="role">{t('orchestration.roleMode')}</option>
            <option value="instance">{t('orchestration.instanceMode')}</option>
        </select>
    </label>;
}
