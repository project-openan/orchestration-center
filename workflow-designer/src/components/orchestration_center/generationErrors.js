// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

export const generationErrorMessage = error => {
    const data = error?.response?.data;
    const detail = data?.detail ?? data?.message ?? data?.error ?? error?.message;
    if (typeof detail === 'string') return detail;
    if (typeof detail?.message === 'string') return [detail.code, detail.message].filter(Boolean).join(': ');
    return 'Generation failed';
};
