import React, { useState, useRef } from 'react';
import { ArrowLeft, Upload, FileText, Link2, Clock, ExternalLink, Loader2 } from 'lucide-react';

const MOCK_PACKAGES = [
    {
        id: 'pkg-001',
        filename: 'RAN_Energy_Saving_Solution_Package.pdf',
        importedAt: '2026-06-10T14:30:00Z',
        pdfUrl: '#',
        workflowId: 'wf-energy-saving-01',
        workflowName: 'RAN Energy Saving Workflow',
    },
    {
        id: 'pkg-002',
        filename: 'SPN_Fault_Handling_Solution_Package.pdf',
        importedAt: '2026-06-09T09:15:00Z',
        pdfUrl: '#',
        workflowId: 'wf-spn-fault-01',
        workflowName: 'SPN Fault Handling Workflow',
    },
    {
        id: 'pkg-003',
        filename: 'Home_Broadband_Complaint_Solution_Package.pdf',
        importedAt: '2026-06-08T16:45:00Z',
        pdfUrl: '#',
        workflowId: 'wf-broadband-01',
        workflowName: 'Home Broadband Complaint Workflow',
    },
];

const formatDate = (dateStr) => {
    const d = new Date(dateStr);
    return d.toLocaleDateString('zh-CN', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit'
    });
};

const SolutionPackages = ({ onBack, onImportPdf, onViewWorkflow, loading, loadingStatus, progress, t }) => {
    const fileInput = useRef(null);
    const [dragOver, setDragOver] = useState(false);

    const handleDrop = (e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files[0];
        if (file && file.type === 'application/pdf') {
            onImportPdf(file);
        }
    };

    const handleFileSelect = (e) => {
        const file = e.target.files[0];
        if (file && file.type === 'application/pdf') {
            onImportPdf(file);
        }
        e.target.value = '';
    };

    return (
        <div className="h-full w-full flex flex-col overflow-hidden animate-in fade-in duration-300">
            <div className="shrink-0 px-10 pt-8 pb-4">
                <button
                    onClick={onBack}
                    className="group flex items-center gap-2 text-xs font-black text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200 transition-all uppercase tracking-[0.2em] mb-6"
                >
                    <ArrowLeft size={16} className="group-hover:-translate-x-1 transition-transform" />
                    {t('orchestration.back_to_options')}
                </button>

                <div
                    onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={handleDrop}
                    onClick={() => fileInput.current?.click()}
                    className={`
                        relative flex flex-col items-center justify-center gap-4 p-10 rounded-3xl border-2 border-dashed cursor-pointer transition-all duration-300
                        ${dragOver
                            ? 'border-amber-400 bg-amber-50 dark:bg-amber-900/10 scale-[1.01]'
                            : 'border-zinc-200 dark:border-zinc-700 bg-zinc-50/50 dark:bg-zinc-800/30 hover:border-amber-300 dark:hover:border-amber-600 hover:bg-amber-50/50 dark:hover:bg-amber-900/5'
                        }
                        ${loading ? 'pointer-events-none opacity-60' : ''}
                    `}
                >
                    {loading ? (
                        <>
                            <Loader2 size={36} className="animate-spin text-amber-500" />
                            <div className="text-center">
                                <p className="text-sm font-black text-zinc-700 dark:text-zinc-300">
                                    {t(loadingStatus)} {Math.floor(progress)}%
                                </p>
                                <div className="mt-3 w-48 h-1.5 bg-zinc-200 dark:bg-zinc-700 rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-gradient-to-r from-amber-500 to-orange-500 rounded-full transition-all duration-300"
                                        style={{ width: `${progress}%` }}
                                    />
                                </div>
                            </div>
                        </>
                    ) : (
                        <>
                            <div className="p-4 rounded-2xl bg-amber-100 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400">
                                <Upload size={28} />
                            </div>
                            <div className="text-center">
                                <p className="text-sm font-black text-zinc-700 dark:text-zinc-300 mb-1">
                                    {t('orchestration.packages_upload_title')}
                                </p>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500">
                                    {t('orchestration.packages_upload_hint')}
                                </p>
                            </div>
                        </>
                    )}
                    <input
                        type="file"
                        ref={fileInput}
                        className="hidden"
                        accept=".pdf"
                        onChange={handleFileSelect}
                    />
                </div>
            </div>

            <div className="flex-1 overflow-y-auto px-10 pb-8 custom-scrollbar">
                <div className="flex items-center gap-3 mb-4 mt-2">
                    <h3 className="text-xs font-black text-zinc-400 dark:text-zinc-500 uppercase tracking-[0.2em]">
                        {t('orchestration.packages_list_title')}
                    </h3>
                    <span className="px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800 text-[10px] font-black text-zinc-500 dark:text-zinc-400">
                        {MOCK_PACKAGES.length}
                    </span>
                </div>

                <div className="space-y-3">
                    {MOCK_PACKAGES.map(pkg => (
                        <div
                            key={pkg.id}
                            className="group p-5 rounded-2xl border border-zinc-100 dark:border-zinc-800 bg-white dark:bg-zinc-900/50 hover:border-amber-200 dark:hover:border-amber-700 hover:shadow-lg transition-all duration-300"
                        >
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-4 min-w-0 flex-1">
                                    <div className="p-2.5 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-500 shrink-0">
                                        <FileText size={20} />
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        <h4 className="text-sm font-black text-zinc-800 dark:text-zinc-200 truncate">
                                            {pkg.filename}
                                        </h4>
                                        <div className="flex items-center gap-2 mt-1">
                                            <Clock size={11} className="text-zinc-400" />
                                            <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                                                {formatDate(pkg.importedAt)}
                                            </span>
                                        </div>
                                    </div>
                                </div>

                                <div className="flex items-center gap-3 shrink-0 ml-4">
                                    <a
                                        href={pkg.pdfUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        onClick={(e) => e.stopPropagation()}
                                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-black uppercase tracking-wider text-zinc-500 dark:text-zinc-400 bg-zinc-50 dark:bg-zinc-800 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20 dark:hover:text-red-400 transition-all"
                                    >
                                        <FileText size={13} />
                                        PDF
                                        <ExternalLink size={11} />
                                    </a>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            onViewWorkflow(pkg.workflowId);
                                        }}
                                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-black uppercase tracking-wider text-white bg-blue-500 hover:bg-blue-600 shadow-sm shadow-blue-500/20 transition-all"
                                    >
                                        <Link2 size={13} />
                                        Workflow
                                        <ChevronRightIcon size={11} />
                                    </button>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

const ChevronRightIcon = ({ size, className }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
        <polyline points="9 18 15 12 9 6" />
    </svg>
);

export default SolutionPackages;
