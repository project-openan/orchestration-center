import {useState} from "react";
import {defaultIp, defaultPort, defaultGateway} from "@/service/api.js";
import {Server, X, Globe, Terminal, Save, Link2, LayoutGrid, Network} from "lucide-react";

const SettingsModal = ({isOpen, onClose, t}) => {
    const [config, setConfig] = useState(() => {
        const saved = localStorage.getItem('server_config');
        return saved ? JSON.parse(saved) : {mode: 'ip', ip: defaultIp, port: defaultPort, gatewayUrl: defaultGateway}
    });

    const handleSave = () => {
        localStorage.setItem('server_config', JSON.stringify(config));
        onClose();
        window.location.reload();
    }

    if (!isOpen) return null;

    return (
        <div
            className={"fixed inset-0 z-[100] flex items-center justify-center p-4 bg-zinc-950/40 backdrop-blur-md animate-in fade-in duration-300"}>
            <div
                className={"bg-white dark:bg-zinc-900 w-full max-w-md rounded-[2.5rem] shadow-2xl border border-zinc-100 dark:border-zinc-800 overflow-hidden"}>
                <div className={"p-6 border-b border-zinc-50 dark:border-zinc-800 flex justify-between items-center"}>
                    <div className={"flex items-center gap-3"}>
                        <div className={"p-2 bg-blue-600 rounded-lg text-white"}>
                            <Server size={20}/>
                        </div>
                        <h2 className={"text-lg font-black dark:text-white"}>Server Connection</h2>
                    </div>
                    <button className={"p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-full transition-colors"}
                            onClick={onClose}>
                        <X size={20} className={"text-zinc-400"}/>
                    </button>
                </div>

                <div className={"p-8 space-y-6"}>
                    {/* Mode Selector */}
                    <div className={"space-y-2"}>
                        <label className={"text-[10px] font-black text-zinc-400 ml-1"}>Connection Mode</label>
                        <div className={"grid grid-cols-2 gap-2 p-1 bg-zinc-50 dark:bg-zinc-800/50 rounded-2xl border border-zinc-100 dark:border-zinc-700"}>
                            <button
                                onClick={() => setConfig({...config, mode: 'ip'})}
                                className={`flex items-center justify-center gap-2 py-2 rounded-xl text-xs font-bold transition-all ${config.mode === 'ip' ? 'bg-white dark:bg-zinc-700 shadow-sm text-blue-600 dark:text-blue-400' : 'text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300'}`}
                            >
                                <LayoutGrid size={14}/> Direct IP
                            </button>
                            <button
                                onClick={() => setConfig({...config, mode: 'nginx'})}
                                className={`flex items-center justify-center gap-2 py-2 rounded-xl text-xs font-bold transition-all ${config.mode === 'nginx' ? 'bg-white dark:bg-zinc-700 shadow-sm text-blue-600 dark:text-blue-400' : 'text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300'}`}
                            >
                                <Network size={14}/> Nginx Gateway
                            </button>
                        </div>
                    </div>

                    {config.mode === 'ip' ? (
                        <>
                            <div className={"space-y-2"}>
                                <label className={"text-[10px] font-black text-zinc-400 ml-1"}>Backend Host (IP)</label>
                                <div className={"relative"}>
                                    <input type={"text"} value={config.ip}
                                           onChange={(e) => setConfig({...config, ip: e.target.value})}
                                           className={"w-full pl-10 pr-4 py-3 bg-zinc-50 dark:bg-zinc-800 border border-zinc-100 dark:border-zinc-700 rounded-xl font-bold focus:ring-4 focus:ring-blue-500/10 outline-none transition-all dark:text-white"}
                                           placeholder={"127.0.0.1"}/>
                                    <Globe size={16} className={"absolute left-3.5 top-3.5 text-zinc-400"}/>
                                </div>
                            </div>

                            <div className={"space-y-2"}>
                                <label className={"text-[10px] font-black text-zinc-400 ml-1"}>Port</label>
                                <div className={"relative"}>
                                    <input type={"text"} value={config.port}
                                           onChange={(e) => setConfig({...config, port: e.target.value})}
                                           className={"w-full pl-10 pr-4 py-3 bg-zinc-50 dark:bg-zinc-800 border border-zinc-100 dark:border-zinc-700 rounded-xl font-bold focus:ring-4 focus:ring-blue-500/10 outline-none transition-all dark:text-white"}
                                           placeholder={"5000"}/>
                                    <Terminal size={16} className={"absolute left-3.5 top-3.5 text-zinc-400"}/>
                                </div>
                            </div>
                        </>
                    ) : (
                        <div className={"space-y-2"}>
                            <label className={"text-[10px] font-black text-zinc-400 ml-1"}>Gateway Base URL</label>
                            <div className={"relative"}>
                                <input type={"text"} value={config.gatewayUrl}
                                       onChange={(e) => setConfig({...config, gatewayUrl: e.target.value})}
                                       className={"w-full pl-10 pr-4 py-3 bg-zinc-50 dark:bg-zinc-800 border border-zinc-100 dark:border-zinc-700 rounded-xl font-bold focus:ring-4 focus:ring-blue-500/10 outline-none transition-all dark:text-white"}
                                       placeholder={defaultGateway}/>
                                <Link2 size={16} className={"absolute left-3.5 top-3.5 text-zinc-400"}/>
                            </div>
                            <p className={"text-[10px] text-zinc-400 italic px-1"}>Example: http://192.168.1.100/orchestration</p>
                        </div>
                    )}

                    <p className={"text-[11px] text-zinc-400 font-medium italic leading-relaxed"}>
                        * Changes require a page reload to apply new service endpoint configurations.
                    </p>
                </div>

                <div
                    className={"p-6 bg-zinc-50/50 dark:bg-zinc-900/50 border-t border-zinc-50 dark:border-zinc-800 flex gap-3"}>
                    <button onClick={onClose}
                            className={"flex-1 py-3 rounded-xl font-black text-xs text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-all"}
                    >
                        Cancel
                    </button>
                    <button onClick={handleSave}
                            className={"flex-1 py-3 rounded-xl text-xs bg-blue-600 text-white shadow-lg shadow-blue-500/20 hover:bg-blue-700 active:scale-95 transition-all flex items-center justify-center gap-2"}
                    >
                        <Save size={16}/> Save Config
                    </button>
                </div>
            </div>
        </div>
    )
}
export default SettingsModal;