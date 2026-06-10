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
import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';

const Tooltip = ({ children, content, side = 'right', sideOffset = 10 }) => {
    const [isOpen, setIsOpen] = useState(false);
    const [coords, setCoords] = useState({ top: 0, left: 0, x: 0, y: 0 });
    const triggerRef = useRef(null);

    const updatePosition = () => {
        if (triggerRef.current) {
            const rect = triggerRef.current.getBoundingClientRect();
            let top = rect.top + window.scrollY;
            let left = rect.left;
            let translateX = 0;
            let translateY = 0;

            if (side === 'right') {
                left = rect.right + sideOffset;
            } else if (side === 'left') {
                left = rect.left - sideOffset;
                translateX = -100;
            } else if (side === 'top') {
                top = rect.top + window.scrollY - sideOffset;
                left = rect.left + rect.width / 2;
                translateX = -50;
                translateY = -100;
            } else if (side === 'bottom') {
                top = rect.bottom + window.scrollY + sideOffset;
                left = rect.left + rect.width / 2;
                translateX = -50;
            }

            setCoords({ top, left, x: translateX, y: translateY });
        }
    };

    const handleMouseEnter = () => {
        updatePosition();
        setIsOpen(true);
    };

    useEffect(() => {
        if (isOpen) {
            window.addEventListener('scroll', updatePosition);
            window.addEventListener('resize', updatePosition);
        }
        return () => {
            window.removeEventListener('scroll', updatePosition);
            window.removeEventListener('resize', updatePosition);
        };
    }, [isOpen]);

    const arrowClass = side === 'right' 
        ? 'top-4 -left-1 border-l border-b rotate-45' 
        : side === 'left' 
        ? 'top-4 -right-1 border-r border-t rotate-45'
        : side === 'top'
        ? 'left-1/2 -bottom-1 -translate-x-1/2 border-r border-b rotate-45'
        : 'left-1/2 -top-1 -translate-x-1/2 border-l border-t rotate-45';

    return (
        <>
            <div
                ref={triggerRef}
                onMouseEnter={handleMouseEnter}
                onMouseLeave={() => setIsOpen(false)}
                className="w-full flex justify-center"
            >
                {children}
            </div>

            {createPortal(
                <AnimatePresence>
                    {isOpen && (
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.95 }}
                            style={{
                                position: 'absolute',
                                top: coords.top,
                                left: coords.left,
                                x: `${coords.x}%`,
                                y: `${coords.y}%`,
                                zIndex: 9999,
                            }}
                            className="pointer-events-none"
                        >
                            <div className="max-w-[340px] p-2.5 bg-gray-900/95 text-white text-sm rounded-lg shadow-2xl border border-gray-700 backdrop-blur-sm relative">
                                {content}
                                <div className={`absolute w-2 h-2 bg-gray-900 border-gray-700 ${arrowClass}`} />
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>,
                document.body
            )}
        </>
    );
};

export default Tooltip;
