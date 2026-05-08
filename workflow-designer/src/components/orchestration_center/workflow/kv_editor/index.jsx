import {useTranslation} from "react-i18next";

const KVEditor = ({title, data = {}, onChange, isDark}) => {
    const {t, i18n} = useTranslation();
    const safeStringify = (val) => {
        if (val === null || val === undefined) return "";
        if (typeof val === 'object') {
            try {
                return JSON.stringify(val);
            } catch (e) {
                return String(val);
            }
        }
        return String(val);
    }

    const tryParse = (val) => {
        if (typeof val !== 'string') return val;
        if ((val.startsWith('{') && val.endsWith('}')) || (val.startsWith('[') && val.endsWith(']'))) {
            try {
                return JSON.parse(val);
            } catch (e) {
                return val;
            }
        }
        return val;
    }

    const handleAdd = (e) => {
        e.preventDefault();
        const newData = {...data, "": ""};
        onChange(newData);
    }

    const handleUpdate = (oldKey, newKey, newValue) => {
        const newData = {...data};
        if (oldKey !== newKey) {
            delete newData[oldKey];
        }
        newData[newKey] = tryParse(newValue);
        onChange(newData);
    }

    const handleRemove = (key) => {
        const newData = {...data};
        delete newData[key];
        onChange(newData);
    }

    const theme = {
        wrapper: isDark ? 'bg-zinc-950/50 border-zinc-800/80 p-3' : 'bg-zinc-50/50 border-zinc-100 p-2',
        title: isDark ? 'text-zinc-500' : 'text-zinc-500',
        addBtn: isDark ? 'bg-zinc-200 text-zinc-950 hover:bg-white shadow-none' : 'bg-zinc-800 text-white hover:bg-zinc-900',
        input: isDark ? 'bg-zinc-900 border-zinc-800 text-zinc-200 focus:border-zinc-500 focus:bg-zinc-800/50' : 'bg-white border-zinc-200 text-zinc-800 focus:border-zinc-400',
        emptyBox: isDark ? 'border-zinc-800 bg-zinc-900/30 text-zinc-600' : 'border-zinc-200 bg-white/50 text-zinc-400',
        removeBtn: isDark ? 'text-zinc-600 hover:text-rose-400' : 'text-zinc-300 hover:text-rose-500',
    }

    return (
        <div className={`space-y-3 mt-4 rounded-xl border transition-all ${theme.wrapper}`}>
            <div className={"flex justify-between items-center px-1"}>
                <span className={`text-[12px] font-bold tracking-wider ${theme.title}`}>
                    {title}
                </span>
                <button type={"button"}
                        onClick={handleAdd}
                        className={`text-[10px] px-2.5 py-1 rounded-md font-bold transition-all active:scale-95 shadow-sm ${theme.addBtn}`}
                >
                    +{t('common.add')}
                </button>
            </div>

            <div className={"space-y-2"}>
                {Object.entries(data).map(([key, value], inx) => (
                    <div key={inx} className={"flex gap-2 items-center group animate-in fade-in slide-in-from-top-1 duration-200"}>
                        <input
                            placeholder={t('workflow.panel.keyPlaceholder')}
                            className={`w-1/3 px-2.5 py-1.5 rounded-lg border text-[12px] font-mono outline-none transition-all shadow-sm ${theme.input}`}
                            value={key}
                            onChange={(e) => handleUpdate(key, e.target.value, value)}
                        />
                        <input
                            placeholder={t('workflow.panel.valuePlaceholder')}
                            className={`flex-1 px-2.5 py-1.5 rounded-lg border text-[12px] outline-none transition-all shadow-sm ${theme.input}`}
                            value={safeStringify(value)}
                            onChange={(e) => handleUpdate(key, key, e.target.value)}
                        />
                        <button type={"button"}
                        onClick={()=> handleRemove(key)}
                                className={`transition-colors p-1 flex-shrink-0 ${theme.removeBtn}`}
                                title={t('common.delete')}
                        >
                            <svg className={"w-4 h-4"} fill={"none"} viewBox={"0 0 24 24"} stroke={"currentColor"}>
                                <path strokeLinecap={"round"} strokeLinejoin={"round"} strokeWidth={2}
                                      d={"M9 7l-.867 12.142A2 2 0 0116.138 21H.862a2 20 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"}/>
                            </svg>
                        </button>
                    </div>
                ))}

                {Object.keys(data).length === 0 && (
                    <div className={`text-[11px] italic text-center py-4 border border-dashed rounded-xl transition-colors ${theme.emptyBox}`}>
                        {t('workflow.panel.noParams')}
                    </div>
                )}
            </div>
        </div>
    )
}

export default KVEditor;
