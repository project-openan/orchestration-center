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

import { Component } from 'react';

export class ErrorBoundary extends Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, errorInfo) {
        console.error('[Portal ErrorBoundary]', error, errorInfo);
    }

    handleReset = () => {
        this.setState({ hasError: false, error: null });
    };

    render() {
        if (this.state.hasError) {
            return (
                <div className="h-full flex items-center justify-center p-8">
                    <div className="text-center max-w-md">
                        <div className="text-4xl mb-4">⚠</div>
                        <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 mb-2">
                            Plugin Error
                        </h2>
                        <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-4">
                            {this.state.error?.message || 'An unexpected error occurred in this plugin.'}
                        </p>
                        <button
                            onClick={this.handleReset}
                            className="px-4 py-2 rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-all text-sm font-medium"
                        >
                            Retry
                        </button>
                    </div>
                </div>
            );
        }
        return this.props.children;
    }
}
