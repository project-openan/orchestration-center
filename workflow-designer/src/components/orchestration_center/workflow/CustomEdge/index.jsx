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
import React, { useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import {
    BaseEdge,
    EdgeLabelRenderer,
    getBezierPath,
} from '@xyflow/react';

export default function CustomEdge({
    id,
    source,
    target,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    style = {},
    markerEnd,
    label,
    data,
}) {
    const [edgePath, labelX, labelY] = getBezierPath({
        sourceX,
        sourceY,
        sourcePosition,
        targetX,
        targetY,
        targetPosition,
    });

    const [isHovered, setIsHovered] = useState(false);
    const [tooltipCoords, setTooltipCoords] = useState({ top: 0, left: 0 });
    const labelRef = useRef(null);
    const requestRef = useRef();

    // Real time calculation of position function
    const updatePosition = () => {
        if (labelRef.current && isHovered) {
            const rect = labelRef.current.getBoundingClientRect();
            // Accurate calculation: Label horizontal center, 8px above the upper edge
            setTooltipCoords({
                top: rect.top - 8,
                left: rect.left + rect.width / 2
            });
            requestRef.current = requestAnimationFrame(updatePosition);
        }
    };

    React.useEffect(() => {
        if (isHovered) {
            updatePosition();
            window.addEventListener('scroll', updatePosition, true);
        } else {
            cancelAnimationFrame(requestRef.current);
            window.removeEventListener('scroll', updatePosition, true);
        }
        return () => {
            cancelAnimationFrame(requestRef.current);
            window.removeEventListener('scroll', updatePosition, true);
        };
    }, [isHovered]);

    if (!label) {
        return <BaseEdge path={edgePath} markerEnd={markerEnd} style={style} />;
    }

    return (
        <>
            <BaseEdge path={edgePath} markerEnd={markerEnd} style={style} />
            <EdgeLabelRenderer>
                <div
                    ref={labelRef}
                    style={{
                        position: 'absolute',
                        transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
                        fontSize: 11,
                        pointerEvents: 'all',
                        zIndex: 0,
                    }}
                    className="nodrag nopan"
                    onMouseEnter={() => setIsHovered(true)}
                    onMouseLeave={() => setIsHovered(false)}
                >
                    <div 
                        className={`
                            px-2.5 py-1 rounded-[6px] border shadow-sm max-w-[200px]
                            transition-all duration-200 hover:scale-105 active:scale-95
                            cursor-help
                            ${style.stroke === '#357BF1' || style.stroke === '#A9C8FB'
                                ? 'bg-white/95 border-cm-line text-cm-muted dark:bg-zinc-900/90 dark:border-zinc-700 dark:text-zinc-400'
                                : 'bg-cm-primary-faint border-cm-primary/25 text-cm-primary dark:bg-cm-primary/15 dark:border-cm-primary/30 dark:text-blue-300 font-medium'}
                        `}
                    >
                        <div className="line-clamp-2 overflow-hidden text-ellipsis break-words text-center leading-tight">
                            {label}
                        </div>
                    </div>
                </div>
            </EdgeLabelRenderer>

            {isHovered && createPortal(
                <div 
                    style={{
                        position: 'fixed',
                        top: tooltipCoords.top,
                        left: tooltipCoords.left,
                        transform: 'translate(-50%, -100%)',
                        zIndex: 999999, // High priority
                        pointerEvents: 'none',
                    }}
                >
                    <div className="flex flex-col items-center">
                        <div className="px-4 py-2.5 bg-[#123253]/97 dark:bg-zinc-800/97 text-white text-[12px] rounded-[10px] shadow-panel border border-white/10 max-w-[280px] whitespace-normal break-words leading-relaxed animate-in fade-in zoom-in-95 duration-200">
                            <div className="max-h-60 overflow-y-auto custom-scrollbar pr-1">
                                {label}
                            </div>
                        </div>
                        {/* Arrow: located directly below the horizontal center */}
                        <div className="w-0 h-0 border-l-[8px] border-l-transparent border-r-[8px] border-r-transparent border-t-[8px] border-t-[#123253]/97 dark:border-t-zinc-800/97" />
                    </div>
                </div>,
                document.body
            )}
        </>
    );
}
