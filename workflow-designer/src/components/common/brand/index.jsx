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
//    distributed under the License is distributed on an "AS IS" BASIS,
//    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//    See the License for the specific language governing permissions and
//    limitations under the License.
import {useTranslation} from "react-i18next";
import markUrl from "@/assets/brand/cmcc-mark.svg";

/**
 * China Mobile brand mark.
 *
 * The artwork already carries the official blue/green pair, so it stays
 * legible on the light canvas as well as on the dark navy surface; callers
 * only decide the plate around it.
 */
export const BrandMark = ({className = "w-7 h-7", alt}) => {
    const {t} = useTranslation();
    return (
        <img
            src={markUrl}
            alt={alt || t('brand.company')}
            className={`object-contain select-none ${className}`}
            draggable={false}
        />
    );
};

/**
 * Mark + wordmark used by the application top bar.
 *
 * `inverse` switches the type to white for the branded login panel;
 * `compact` hides the product name on narrow viewports.
 */
export const BrandLockup = ({compact = false, inverse = false}) => {
    const {t} = useTranslation();
    return (
        <div className="flex items-center gap-2.5 min-w-0">
            <span
                className={`h-7 w-7 shrink-0 grid place-items-center rounded-[7px] p-1
                ${inverse ? 'bg-white/95' : 'bg-white border border-cm-line shadow-[inset_0_1px_1px_rgba(255,255,255,0.6)] dark:bg-zinc-800 dark:border-zinc-700'}`}
            >
                <BrandMark className="w-full h-full"/>
            </span>
            <span className={`text-[16px] font-bold tracking-[-0.45px] whitespace-nowrap
                ${inverse ? 'text-white' : 'text-[#142843] dark:text-zinc-100'}`}>
                {t('brand.company')}
            </span>
            {!compact && (
                <>
                    <span className={`h-3.5 w-px ${inverse ? 'bg-white/30' : 'bg-cm-line-strong'}`}/>
                    <span className={`hidden sm:inline text-[13px] whitespace-nowrap
                        ${inverse ? 'text-white/80' : 'text-cm-secondary dark:text-zinc-400'}`}>
                        {t('brand.product')}
                    </span>
                </>
            )}
        </div>
    );
};

export default BrandMark;
