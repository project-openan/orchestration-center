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
import {useTranslation} from "react-i18next";
import {Lock, X, Save, AlertCircle, Loader2, KeyRound} from "lucide-react";
import {changePassword} from "@/service/api.js";

const PasswordChangeModal = ({isOpen, onClose, t, forced = false}) => {
    const [oldPassword, setOldPassword] = useState("");
    const [newPassword, setNewPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    if (!isOpen) return null;

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!oldPassword.trim() || !newPassword.trim() || loading) return;
        if (newPassword.length < 8) {
            setError(t('login.password_too_short'));
            return;
        }
        if (!/[A-Z]/.test(newPassword) || !/[a-z]/.test(newPassword) || !/[0-9]/.test(newPassword)) {
            setError(t('login.password_complexity'));
            return;
        }
        if (newPassword !== confirmPassword) {
            setError(t('login.password_mismatch'));
            return;
        }
        setLoading(true);
        setError("");
        try {
            await changePassword(oldPassword, newPassword);
            onClose();
            window.location.reload();
        } catch (err) {
            const msg = err?.response?.data?.message || err?.message || "";
            setError(msg || t('login.error'));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className={"fixed inset-0 z-[100] flex items-center justify-center p-4 bg-[#112742]/32 backdrop-blur-sm animate-in fade-in duration-300"}>
            <div className={"bg-white dark:bg-zinc-900 w-full max-w-md rounded-3xl shadow-modal border border-zinc-100 dark:border-zinc-800 overflow-hidden"}>
                <div className={"p-6 border-b border-zinc-50 dark:border-zinc-800 flex justify-between items-center"}>
                    <div className={"flex items-center gap-3"}>
                        <div className={"p-2 bg-cm-primary rounded-[7px] text-white"}>
                            <KeyRound size={20}/>
                        </div>
                        <h2 className={"text-[16px] font-bold dark:text-white"}>{t('login.change_password')}</h2>
                    </div>
                    {!forced && (
                        <button className={"p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-full transition-colors"} onClick={onClose}>
                            <X size={20} className={"text-zinc-400"}/>
                        </button>
                    )}
                </div>
                <form onSubmit={handleSubmit} className={"p-8 space-y-5"}>
                    {forced && (
                        <div className={"flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/40 rounded-xl p-3"}>
                            <AlertCircle size={16} className={"shrink-0"}/>
                            <span>{t('login.must_change_password')}</span>
                        </div>
                    )}
                    <div className={"space-y-2"}>
                        <label className={"text-[11px] font-semibold text-cm-muted ml-1"}>{t('login.current_password')}</label>
                        <div className={"relative"}>
                            <input type={"password"} value={oldPassword}
                                   onChange={(e) => setOldPassword(e.target.value)}
                                   placeholder={t('login.current_password')}
                                   autoFocus
                                   disabled={loading}
                                   className={"w-full pl-10 pr-4 py-3 bg-zinc-50 dark:bg-zinc-800 border border-zinc-100 dark:border-zinc-700 rounded-xl font-bold focus:ring-4 focus:ring-blue-500/10 outline-none transition-all dark:text-white text-sm"}
                                   required/>
                            <Lock size={16} className={"absolute left-3.5 top-3.5 text-zinc-400"}/>
                        </div>
                    </div>
                    <div className={"space-y-2"}>
                        <label className={"text-[11px] font-semibold text-cm-muted ml-1"}>{t('login.new_password')}</label>
                        <div className={"relative"}>
                            <input type={"password"} value={newPassword}
                                   onChange={(e) => setNewPassword(e.target.value)}
                                   placeholder={t('login.new_password')}
                                   disabled={loading}
                                   className={"w-full pl-10 pr-4 py-3 bg-zinc-50 dark:bg-zinc-800 border border-zinc-100 dark:border-zinc-700 rounded-xl font-bold focus:ring-4 focus:ring-blue-500/10 outline-none transition-all dark:text-white text-sm"}
                                   required/>
                            <Lock size={16} className={"absolute left-3.5 top-3.5 text-zinc-400"}/>
                        </div>
                    </div>
                    <div className={"space-y-2"}>
                        <label className={"text-[11px] font-semibold text-cm-muted ml-1"}>{t('login.confirm_password')}</label>
                        <div className={"relative"}>
                            <input type={"password"} value={confirmPassword}
                                   onChange={(e) => setConfirmPassword(e.target.value)}
                                   placeholder={t('login.confirm_password')}
                                   disabled={loading}
                                   className={"w-full pl-10 pr-4 py-3 bg-zinc-50 dark:bg-zinc-800 border border-zinc-100 dark:border-zinc-700 rounded-xl font-bold focus:ring-4 focus:ring-blue-500/10 outline-none transition-all dark:text-white text-sm"}
                                   required/>
                            <Lock size={16} className={"absolute left-3.5 top-3.5 text-zinc-400"}/>
                        </div>
                    </div>
                    {error && (
                        <div className={"flex items-center gap-2 text-sm text-red-500"}>
                            <AlertCircle size={16}/>
                            <span>{error}</span>
                        </div>
                    )}
                    <div className={"flex gap-3 pt-2"}>
                        {!forced && (
                            <button type={"button"} onClick={onClose}
                                    className={"cm-btn flex-1 min-h-[39px] text-[13px] text-cm-muted"}>
                                {t('common.cancel')}
                            </button>
                        )}
                        <button type={"submit"} disabled={loading}
                                className={"cm-btn-primary flex-1 min-h-[39px] text-[13px]"}>
                            {loading ? (<><Loader2 size={16} className="animate-spin"/> {t('login.loading')}</>) : (<><Save size={16}/> {t('login.change_password')}</>)}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

export default PasswordChangeModal;
