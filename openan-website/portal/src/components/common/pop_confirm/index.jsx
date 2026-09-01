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
import {useRef, useState} from "react";
import {useTranslation} from "react-i18next";
import {createPortal} from "react-dom";
import {AnimatePresence, motion} from "framer-motion";

const DeleteConfirm = ({children, onConfirm, title, isDark}) => {
    const {t} = useTranslation();
    const [isOpen, setIsOpen] = useState(false);
    const [coords, setCoords] = useState({top: 0, left: 0});
    const triggerRef = useRef(null);

    const toggleOpen = (e) => {
        e.stopPropagation();
        if (triggerRef.current) {
            const rect = triggerRef.current.getBoundingClientRect();
            setCoords({
                top: rect.top + window.scrollY - 10,
                left: rect.left - 160
            });
            setIsOpen(!isOpen);
        }
    }

    return (
        <>
            <div ref={triggerRef} onClick={toggleOpen} className={"w-fit cursor-pointer"}>
                {children}
            </div>

            {createPortal(
                <AnimatePresence>
                    {isOpen && (
                        <>
                            <div className={"fixed inset-0 z-[9998]"} onClick={() => setIsOpen(false)}/>

                            <motion.div initial={{opacity: 0, scale: 0.95, x: 10}}
                                        animate={{opacity: 1, scale: 1, x: 0}}
                                        exit={{opacity: 0, scale: 0.95, x: 10}}
                                        style={{
                                            position: 'absolute',
                                            top: coords.top,
                                            left: coords.left,
                                            zIndex: 9999
                                        }}>
                                <div className={`w-[160px] p-3 rounded-xl shadow-2xl border transition-all ${
                                    isDark ? 'bg-slate-800 border-slate-700 text-slate-200'
                                        : 'bg-white border-slate-200 text-slate-900'
                                }`}>
                                    <p className={"text-xs mb-3 font-medium leading-relaxed"}>
                                        {title || t('common.confirm_delete')}
                                    </p>
                                    <div className={"flex gap-2 justify-end"}>
                                        <button onClick={(e) => {
                                            e.stopPropagation();
                                            setIsOpen(false);
                                        }}
                                                className={"px-2 py-1 text-[11px] hover:bg-slate-100 dark:hover:bg-slate-700 rounded transition-colors"}>
                                            {t('common.cancel')}
                                        </button>
                                        <button onClick={(e) => {
                                            e.stopPropagation();
                                            onConfirm();
                                            setIsOpen(false);
                                        }}
                                                className={"px-2 py-1 text-[11px] bg-red-500 text-white rounded hover:bg-red-600 transition-colors shadow-sm"}>
                                            {t('common.confirm')}
                                        </button>
                                    </div>
                                    <div
                                        className={`absolute top-1/2 -right-1 -translate-y-1/2 w-2 h-2 rotate-45 border-t border-r ${
                                            isDark ? 'bg-slate-800 border-slate-700' : 'bg-white border-slate-200'
                                        }`}/>
                                </div>
                            </motion.div>
                        </>
                    )}
                </AnimatePresence>,
                document.body
            )}
        </>
    )
}

export default DeleteConfirm;