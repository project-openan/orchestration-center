import { Handle, Position, useConnection } from "@xyflow/react";
import { useTranslation } from "react-i18next";

export const StartNode = ({ selected }) => {
    const connection = useConnection();
    const { t } = useTranslation();
    const isConnecting = connection.inProgress;

    const handleBaseStyle = `
        !w-[8px] !h-[8px] !bg-emerald-400 border-2 border-white 
        transition-all duration-300 ease-out cursor-crosshair
        hover:!w-[14px] hover:!h-[14px] hover:shadow-lg
        z-[110]
        
        /* 连线起点反馈 */
        [&.react-flow__handle-connecting]:ring-4 [&.react-flow__handle-connecting]:ring-emerald-500/20
        
        /* 隐形热区 */
        after:content-[''] after:absolute after:top-1/2 after:left-1/2 after:-translate-x-1/2 after:-translate-y-1/2 
        after:w-[60px] after:h-[60px] after:bg-transparent
    `;

    return (
        <div className={`
            w-16 h-16 rounded-full bg-emerald-500 shadow-lg border-4 border-white flex items-center justify-center text-white font-bold text-sm relative group transition-all
            ${selected ? 'ring-2 ring-emerald-500 ring-offset-2' : ''}
        `}>
            <div className={"absolute -top-8 left-1/2 -translate-x-1/2 bg-slate-800 text-white text-[10px] px-2 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap"}>
                {t('node_label.start')}
            </div>
            START

            {/* Start nodes only have Right Source for L-R flow */}
            <Handle type={"source"} position={Position.Right} id={"s-right"} style={{ top: '50%' }} className={handleBaseStyle} />
        </div>
    );
};

export const EndNode = ({ selected }) => {
    const connection = useConnection();
    const { t } = useTranslation();
    const isConnecting = connection.inProgress;

    const targetHandleBaseClasses = `
        !w-0 !h-0 !bg-transparent !border-0 !absolute !transform-none
        z-[100]
        after:content-[''] after:absolute after:bg-transparent
        ${isConnecting ? 'after:pointer-events-auto' : 'after:pointer-events-none'}
    `;

    return (
        <div className={`
            w-16 h-16 rounded-full bg-rose-500 shadow-lg border-4 border-white flex items-center justify-center text-white font-bold text-sm relative group transition-all
            ${selected ? 'ring-2 ring-rose-500 ring-offset-2' : ''}
        `}>
            <div className={"absolute -top-8 left-1/2 -translate-x-1/2 bg-slate-800 text-white text-[10px] px-2 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap"}>
                {t('node_label.end')}
            </div>
            END

            {/* End nodes only have Left Target (whole node) for L-R flow */}
            <Handle type="target" position={Position.Left} id="t-left" style={{ left: 0, top: '50%' }} className={`${targetHandleBaseClasses} after:w-[64px] after:h-[64px] after:left-[32px] after:top-0 after:-translate-x-1/2 after:-translate-y-1/2`} />
        </div>
    );
};
