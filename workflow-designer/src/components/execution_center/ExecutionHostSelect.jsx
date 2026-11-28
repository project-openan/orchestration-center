// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import React from 'react';

export default function ExecutionHostSelect({ className, hosts, label, value, onChange }) {
    return (
        <select aria-label={label} className={className} value={value} onChange={event => onChange(event.target.value)}>
            <option value="">{label}</option>
            {hosts.map(agent => <option key={agent.name} value={agent.name}>{agent.name}</option>)}
        </select>
    );
}
