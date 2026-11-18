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
//    distributed under the License is distributed on an "AS IS" BASIS,
//    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//    See the License for the specific language governing permissions and
//    limitations under the License.

// ---------------------------------------------------------------------------
// China Mobile visual identity.
//
// The tokens mirror the group AI-platform reference design that ships with the
// deployment: a #F5F8FE canvas, white cards with #E1E9F6 hairlines and a very
// light navy shadow, #2464E8 as the primary action colour, #E9F3FF for the top
// bar and a 13px base type scale.
//
// Two mappings make the restyle tractable without touching every className:
//   * `zinc`/`slate` (the app's neutral ramps) are remapped to the blue-grey
//     scale the reference uses, so surfaces, borders and text pick up the
//     temperature automatically in both light and dark mode.
//   * `blue` (the accent ramp) is remapped to the brand ramp, so existing
//     primary controls already render on brand.
// Semantic colours (emerald/amber/rose) keep their meaning; indigo/violet/
// purple collapse into the same blue family so decorative accents stay on
// brand instead of reading as a rainbow.
// ---------------------------------------------------------------------------

const neutral = {
    50: '#F5F8FE',
    100: '#EEF3FB',
    200: '#E1E9F6',
    300: '#CFDBEC',
    400: '#94A9C2',
    500: '#7188AA',
    600: '#506988',
    700: '#33496A',
    800: '#1D3352',
    900: '#142843',
    950: '#0C1B2E',
};

const brand = {
    50: '#F2F7FF',
    100: '#E7F0FF',
    200: '#D3E3FF',
    300: '#A9C8FB',
    400: '#6E9DF4',
    500: '#357BF1',
    600: '#2464E8',
    700: '#1B4FD1',
    800: '#1D45AA',
    900: '#1D3F87',
    950: '#152A57',
};

const brandAlt = {
    50: '#F1F6FF',
    100: '#E5EDFF',
    200: '#CBDCFB',
    300: '#9FBEF2',
    400: '#6C97E4',
    500: '#4579D2',
    600: '#2F60B6',
    700: '#284F93',
    800: '#234276',
    900: '#1F3862',
    950: '#152540',
};

export default {
    darkMode: 'class',
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    plugins: [
        require('@tailwindcss/typography'),
    ],
    theme: {
        extend: {
            colors: {
                zinc: neutral,
                slate: neutral,
                gray: neutral,
                blue: brand,
                indigo: brandAlt,
                violet: brandAlt,
                purple: brandAlt,

                brand: {
                    ...brand,
                    DEFAULT: '#2464E8',
                },
                cmcc: {
                    blue: '#0084CF',
                    'blue-deep': '#00639E',
                    cyan: '#00A3E0',
                    green: '#8DC21F',
                    'green-deep': '#5E9B00',
                },
                cm: {
                    canvas: '#F5F8FE',
                    'canvas-soft': '#F7F9FE',
                    tint: '#EAF2FE',
                    surface: '#FFFFFF',
                    line: '#E1E9F6',
                    'line-soft': '#EAF0F8',
                    'line-strong': '#CFDBEC',
                    ink: '#172D4D',
                    'ink-strong': '#142843',
                    heading: '#18304D',
                    secondary: '#506988',
                    muted: '#7188AA',
                    faint: '#94A9C2',
                    primary: '#2464E8',
                    'primary-hover': '#1758D7',
                    'primary-soft': '#EEF5FF',
                    'primary-faint': '#E7F0FF',
                    sky: '#EAF3FF',
                    topbar: '#E9F3FF',
                    'topbar-line': '#CDDFF7',
                    accent: '#2B61CD',
                    night: '#0C1B2E',
                },
            },
            fontFamily: {
                sans: [
                    'Inter',
                    '"Microsoft YaHei"',
                    '"PingFang SC"',
                    'ui-sans-serif',
                    'system-ui',
                    '-apple-system',
                    'BlinkMacSystemFont',
                    '"Segoe UI"',
                    'Arial',
                    'sans-serif',
                ],
                mono: ['ui-monospace', 'SFMono-Regular', 'Consolas', 'monospace'],
            },
            fontSize: {
                '2xs': ['10px', {lineHeight: '14px'}],
                '3xs': ['9px', {lineHeight: '12px'}],
            },
            borderRadius: {
                cm: '10px',
                'cm-sm': '7px',
                'cm-panel': '11px',
                lg: '7px',
                xl: '10px',
                '2xl': '12px',
                '3xl': '14px',
                '4xl': '18px',
            },
            boxShadow: {
                card: '0 3px 14px rgba(37, 86, 151, 0.045)',
                'card-hover': '0 8px 20px rgba(29, 94, 209, 0.09)',
                panel: '0 18px 60px rgba(15, 49, 81, 0.16)',
                modal: '0 22px 90px rgba(15, 49, 81, 0.22)',
                brand: '0 3px 8px rgba(39, 104, 236, 0.16)',
                'brand-sm': '0 2px 6px rgba(39, 104, 236, 0.14)',
                inset: 'inset 0 1px 0 rgba(255, 255, 255, 0.6)',
            },
            backgroundImage: {
                'brand-gradient': 'linear-gradient(145deg, #39B7D7 0%, #1766D9 100%)',
                'brand-button': 'linear-gradient(145deg, #357BF1 0%, #2464E8 100%)',
                'avatar-gradient': 'linear-gradient(145deg, #4789FF 0%, #1556D4 100%)',
                'topbar-sheen': 'linear-gradient(180deg, #ECF5FF 0%, #E9F3FF 100%)',
            },
            keyframes: {
                fadeIn: {
                    from: {opacity: 0, transform: 'translateY(6px)'},
                    to: {opacity: 1, transform: 'translateY(0)'},
                },
            },
        },
    }
}
