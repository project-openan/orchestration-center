import { useState } from "react";
import { Check, Copy, FileJson } from "lucide-react";
import { useTranslation } from "react-i18next";

const CodeInspector = ({ data, fileName = 'manifest.json', isDark = false }) => {
    const { t } = useTranslation();
    const [copied, setCopied] = useState(false);

    const handleCopy = () => {
        navigator.clipboard.writeText(JSON.stringify(data, null, 2));
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }

    const jsonString = JSON.stringify(data, null, 4);

    return (<div className={`flex h-full flex-col transition-all duration-300 ${isDark ? 'dark' : ''}`}>
        <div className={`flex-1 rounded-[1rem] border shadow-2xl overflow-hidden flex flex-col relative transition-colors duration-300 ${isDark ? 'bg-zinc-950 border-zinc-800 shadow-black/50' : 'bg-zinc-50 border-zinc-200 shadow-zinc-200/50'}`}>
            <div className={`flex items-center justify-between px-6 py-2 border-b backdrop-blur-md sticky top-0 z-10 transition-colors ${isDark ? 'bg-zinc-950/80 border-zinc-800' : 'bg-zinc-200/50 border-zinc-200'}`}>
                <div className={"flex items-center gap-4"}>
                    <div className={`flex items-center gap-2 px-3 py-1 rounded-md ${isDark ? 'bg-zinc-800' : 'bg-white shadow-sm'}`}>
                        <FileJson size={12} className={isDark ? 'text-blue-400' : 'text-blue-600'} />
                        <span className={`text-[12px] font-black  leading-none ${isDark ? 'text-zinc-400' : 'text-zinc-600'}`}>
                            {fileName}
                        </span>
                    </div>
                </div>

                <button onClick={handleCopy}
                    className={`relative flex items-center justify-center w-9 h-9 rounded-xl transition-all duration-200 active:scale-95 ${isDark
                        ? 'bg-zinc-800 text-zinc-400 hover:bg-blue-600/20 hover:text-blue-400 border border-zinc-700/50 hover:border-blue-500/50'
                        : 'bg-white text-zinc-600 border border-zinc-200 shadow-sm hover:border-blue-500 hover:text-blue-600'}`}
                    title={copied ? t('common.copied') : t('common.copy_raw_json')}>
                    <div className={`transition-all duration-300 ${copied ? 'scale-0 opacity-0' : 'scale-100 opacity-100'}`}>
                        <Copy size={16} strokeWidth={2.5} />
                    </div>
                    <div className={`absolute transition-all duration-300 ${copied ? 'scale-100 opacity-100' : 'scale-0 opacity-0'}`}>
                        <Check size={18} strokeWidth={3} className={"text-emerald-500"} />
                    </div>
                </button>
            </div>

            <div className={"flex-1 overflow-auto custom-scrollbar p-8"}>
                <pre className={"font-mono text-sm leading-relaxed selection:bg-blue-500/30"}>
                    <code className={`whitespace-pre transition-colors duration-0 ${isDark ? 'text-emerald-400/90' : 'text-blue-700'}`}>
                        {jsonString}
                    </code>
                </pre>
            </div>

            <div className={`px-6 py-2 border-t flex justify-end transition-colors ${isDark ? 'bg-zinc-900/30 border-zinc-800' : 'bg-zinc-100/50 border-zinc-200'}`}>
                <span className={`text-[10px] font-bold uppercase tracking-widest ${isDark ? 'text-zinc-600' : 'text-zinc-400'}`}>
                    UTF-8 · JSON · {jsonString.length} {t('common.chars')}
                </span>
            </div>
        </div>
    </div>);
};

export default CodeInspector;
