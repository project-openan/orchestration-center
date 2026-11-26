// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from 'react-i18next';

export default function GenerationMode({ value, onChange, disabled }) {
    const { t } = useTranslation();
    return <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-200">
        {t('orchestration.generationMode')}
        <select aria-label={t('orchestration.generationMode')} value={value} disabled={disabled}
            onChange={event => onChange(event.target.value)}
            className="rounded-lg border border-zinc-300 bg-white text-zinc-800 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100">
            <option value="role">{t('orchestration.roleMode')}</option>
            <option value="instance">{t('orchestration.instanceMode')}</option>
        </select>
    </label>;
}
