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
import {useInternalNode} from "@xyflow/react";
import {getEdgeParams} from "./utils.js";
import {BaseEdge, getStraightPath} from "@xyflow/react";

function FloatingEdge({id, source, target, markerEnd, style}) {
    const sourceNode = useInternalNode(source);
    const targetNode = useInternalNode(target);

    if (!sourceNode || !targetNode) {
        return null;
    }
    const {sx, sy, tx, ty} = getEdgeParams(sourceNode, targetNode);

    const [path] = getStraightPath({
        sourceX: sx,
        sourceY: sy,
        targetX: tx,
        targetY: ty,
    });

    return (
        <BaseEdge path={path} id={id} markerEnd={markerEnd} style={style} className={"react-flow__edge-path"}/>
    )
}

export default FloatingEdge;