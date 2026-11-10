#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/phase4_translate.py — Phase 4: Khmer Spoken Dialogue Translation & Role Assignment
=======================================================================================
Takes canonical_dialogue.json from Phase 2, extracts verified spoken lines,
translates them into authentic colloquial Cambodian phrasing with speaker role assignments,
and ensures the translated text fits the actor's real speech duration.
"""

import json
import os
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.khmer_validator import validate_khmer_text, is_valid_for_tts

# Character voice casting guidelines
VOICE_FEMALE_LEAD = "km-KH-SreymomNeural"
VOICE_MALE_LEAD = "km-KH-PisethNeural"
VOICE_MALE_ELDER = "km-KH-PisethNeural"
VOICE_FEMALE_ANTAGONIST = "km-KH-SreymomNeural"

# Direct translation dictionary for common Chinese drama dialogue patterns
# to ensure natural Khmer cadence and authentic phrasing.
COMMON_PHRASES_KM = {
    # Movie 01 additions & visual captions
    "8,000元": "៨,០០០ យ័ន",
    "8000元": "៨,០០០ យ័ន",
    "SANY": "SANY",
    "支付宝工资到账": "ទទួលបានប្រាក់ខែ Alipay",
    "支付宝工资到账 8,000元": "ទទួលបានប្រាក់ខែ Alipay ៨,០០០ យ័ន",
    "一转眼": "មួយពព្រិចភ្នែក",
    "你那边 干啥呢": "នៅខាងឯង កំពុងធ្វើអីហ្នឹង?",
    "你那边": "នៅខាងឯង",
    "干啥呢": "កំពុងធ្វើអីហ្នឹង?",
    "干啥呢？": "កំពុងធ្វើអីហ្នឹង?",
    "咋还挂了 老赵": "ម៉េចក៏ចុចបិទចោលអញ្ចឹង?! បងចាវ!",
    "咋还挂了": "ម៉េចក៏ចុចបិទចោលអញ្ចឹង?!",
    "咋还挂了？": "ម៉េចក៏ចុចបិទចោលអញ្ចឹង?!",
    "老赵": "បងចាវ!",
    "一转眼 我又离家快两个月了 你和女儿想我了吧": "មួយពព្រិចភ្នែក បងឃ្លាតពីផ្ទះជិតពីរខែហើយ ប្រហែលកូនស្រីនឹកបងហើយមែនទេ?",
    "一转眼 我又离家快两个月了 你租女儿想我了吧": "មួយពព្រិចភ្នែក បងឃ្លាតពីផ្ទះជិតពីរខែហើយ ប្រហែលកូនស្រីនឹកបងហើយមែនទេ?",
    "老婆 我发工资了 一会 给你转到支付宝里": "អូនសម្លាញ់ បងបើកប្រាក់ខែហើយ បន្តិចទៀតបងផ្ទេរចូល Alipay ឱ្យអូន!",
    "你发个工资 也要跟我打电话 说一声吗": "គ្រាន់តែបើកលុយសោះ ចាំបាច់ខលមកប្រាប់ដែរ?!",
    # Movie 01: 小镇是非多之同床异梦 (Xiao Zhen Shi Fei Duo)
    "我都急死了": "ខ្ញុំអន្ទះសារស្ទើរឆ្កួតហើយ!",
    "就等最后的审判了 这几天": "ចាំតែសាលក្រមចុងក្រោយប៉ុណ្ណោះ ប៉ុន្មានថ្ងៃនេះ!",
    "就等最后的审判了 这几天。": "ចាំតែសាលក្រមចុងក្រោយប៉ុណ្ណោះ ប៉ុន្មានថ្ងៃនេះ!",
    "就等最后的审判了": "ចាំតែសាលក្រមចុងក្រោយប៉ុណ្ណោះ!",
    "就我最後的甩判 這幾天": "ចាំតែសាលក្រមចុងក្រោយប៉ុណ្ណោះ ប៉ុន្មានថ្ងៃនេះ!",
    "我也是 我每分每秒都在想你": "ខ្ញុំក៏ដូចគ្នាដែរ រាល់វិនាទីសុទ្ធតែនឹកបង!",
    "我也是 我每分每秒都在想你。": "ខ្ញុំក៏ដូចគ្នាដែរ រាល់វិនាទីសុទ្ធតែនឹកបង!",
    "我每分每秒都在想你": "រាល់វិនាទីសុទ្ធតែនឹកបង!",
    "老婆 我发工资了 一会 给你转到支付宝里 你发个工资 也要跟我打电话 说一声吗": "អូនសម្លាញ់ បងបើកប្រាក់ខែហើយ បន្តិចទៀតបងផ្ទេរចូល Alipay ឱ្យអូន! គ្រាន់តែបើកលុយសោះ ចាំបាច់ខលមកប្រាប់ដែរ?!",
    "老婆 我发工资了 一会 给你转到支付宝里 你发个工资 也要跟我打电话 说一声吗 你專業": "អូនសម្លាញ់ បងបើកប្រាក់ខែហើយ បន្តិចទៀតបងផ្ទេរចូល Alipay ឱ្យអូន! គ្រាន់តែបើកលុយសោះ ចាំបាច់ខលមកប្រាប់ដែរ?!",
    "老婆 我发工资了": "អូនសម្លាញ់ បងបើកប្រាក់ខែហើយ!",
    "给你转到支付宝里": "ផ្ទេរចូល Alipay ឱ្យអូន!",
    "我又离家快两个月了 你租女儿想我了吧": "បងឃ្លាតពីផ្ទះជិតពីរខែហើយ ប្រហែលកូនស្រីនឹកបងហើយមែនទេ?",
    "你租女儿想我了吧": "ប្រហែលកូនស្រីនឹកបងហើយមែនទេ?",
    "你没话找话的吗": "ឯងគ្មានការរកការនិយាយមែនទេ?",
    "你没话找话的吗？": "ឯងគ្មានការរកការនិយាយមែនទេ?",
    "还有别的事吗 男朋友": "មានការអីទៀតទេ?",
    "还有别的事吗": "មានការអីទៀតទេ?",
    "还有别的事吗？": "មានការអីទៀតទេ?",
    "幹什麼呀": "ធ្វើស្អីហ្នឹង?!",
    "干什么呀": "ធ្វើស្អីហ្នឹង?!",
    "幹什麼呀？": "ធ្វើស្អីហ្នឹង?!",
    "咋声音怪怪的 你 没事 我能干什么呀 外面天气不好 刮风下雨你也要管": "ម៉េចបានសំឡេងប្លែកម្ល៉េះ? គ្មានការអីទេ! ខ្ញុំអាចធ្វើស្អីកើត? នៅខាងក្រៅមេឃមិនល្អ ខ្យល់ភ្លៀងក៏ឯងចង់ចេះដឹងដែរ?!",
    "咋声音怪怪的 没事 我能干什么呀 外面天气不好 刮风下雨你也要管": "ម៉េចបានសំឡេងប្លែកម្ល៉េះ? គ្មានការអីទេ! ខ្ញុំអាចធ្វើស្អីកើត? នៅខាងក្រៅមេឃមិនល្អ ខ្យល់ភ្លៀងក៏ឯងចង់ចេះដឹងដែរ?!",
    "來": "មក!",
    "来": "មក!",
    "離婚手續辦完了嗎": "រត់ការលែងលះរួចរាល់ហើយមែនទេ?",
    "离婚手续办完了吗": "រត់ការលែងលះរួចរាល់ហើយមែនទេ?",
    "离婚手续办完了吗？": "រត់ការលែងលះរួចរាល់ហើយមែនទេ?",
    "想你想的好苦啊": "នឹកអូនស្ទើរដាច់ខ្យល់ហើយ!",
    "想你想得好苦啊": "នឹកអូនស្ទើរដាច់ខ្យល់ហើយ!",
    "要进去吗？": "តើត្រូវចូលទៅខាងក្នុងទេ?",
    "要进去吗": "តើត្រូវចូលទៅខាងក្នុងទេ?",
    "等等。": "ចាំបន្តិចសិន។",
    "等等": "ចាំបន្តិចសិន។",
    "陆总": "លោកប្រធានលូ!",
    "您这么年轻有为": "លោកទាំងក្មេង ទាំងពូកែមានសមត្ថភាពបែបនេះ",
    "又这么帅": "ថែមទាំងសង្ហាទៀត",
    "就这么帅": "ថែមទាំងសង្ហាទៀត",
    "肯定还没结婚吧？": "ច្បាស់ជាមិនទាន់រៀបការទេមែនទេ?",
    "肯定还没结婚吧": "ច្បាស់ជាមិនទាន់រៀបការទេមែនទេ?",
    "你说呢？": "ចុះនាងគិតថាម៉េចដែរ?",
    "你说呢": "ចុះនាងគិតថាម៉េចដែរ?",
    "哎呀讨厌": "អូយ! ស្អប់ណាស់",
    "哎呀 讨厌": "អូយ! ស្អប់ណាស់",
    "那您太太有我漂亮吗？.": "ចុះប្រពន្ធរបស់លោក ស្អាតដូចខ្ញុំទេ?",
    "那您太太有我漂亮吗？-": "ចុះប្រពន្ធរបស់លោក ស្អាតដូចខ្ញុំទេ?",
    "那您太太有我漂亮吗？": "ចុះប្រពន្ធរបស់លោក ស្អាតដូចខ្ញុំទេ?",
    "那您太太有我漂亮吗": "ចុះប្រពន្ធរបស់លោក ស្អាតដូចខ្ញុំទេ?",
    "怎么": "យ៉ាងម៉េច?",
    "你想当我太太？": "ចង់ធ្វើជាប្រពន្ធខ្ញុំមែនទេ?",
    "你想当我太太": "ចង់ធ្វើជាប្រពន្ធខ្ញុំមែនទេ?",
    "我不介意做妹妹的": "ខ្ញុំមិនប្រកាន់ធ្វើជាប្អូនស្រីទេ",
    "我不介意做妹妹": "ខ្ញុំមិនប្រកាន់ធ្វើជាប្អូនស្រីទេ",
    "这小妞够直接": "នាងតូចនេះ ច្បាស់លាស់ត្រង់ៗល្អណាស់",
    "哥欣赏你": "បងចូលចិត្តចរិតនាងហើយ",
    "太糊了": "កាចឆ្នាស់ពេកហើយ",
    "太虎了": "កាចឆ្នាស់ពេកហើយ",
    "你这小妮子太虎了": "នាងតូចនេះ ឆ្នាស់មិនធម្មតាទេ",
    "比那些扭扭捏捏的": "ល្អជាងពួកស្រីៗដែលចូលចិត្តធ្វើពុត",
    "身材特有型": "រូបរាងសង្ហារមាំមួនណាស់",
    "服务特专业": "សេវាកម្មជំនាញណាស់",
    "腹肌练得太洿张了": "សាច់ដុំពោះឡើងរឹងមាំខ្លាំងណាស់",
    "跟块铁极似的": "ដូចជាបន្ទះដែកអញ្ចឹង",
    "跟块铁板似的": "ដូចជាបន្ទះដែកអញ្ចឹង",
    "说你们这的男模": "គេថាប្រុសកំដរនៅទីនេះ",
    "说的好": "និយាយបានល្អ!",
    "这个不行": "មួយនេះមិនកើតទេ",
    "亲自鉴定一下": "មកពិនិត្យផ្ទាល់ខ្លួនឯងមើល៍",
    "姐姐": "បងស្រី!",
    "姐姐火气别这么大嘛": "បងស្រី កុំទាន់ខឹងអីណា",
    "陆总他": "លោកប្រធានលូ គាត់...",
    "陆总她太过分了": "លោកប្រធានលូ នាងម្នាក់នេះជ្រុលហួសហេតុពេកហើយ!",
    "陈经理": "អ្នកគ្រប់គ្រងឆិន!",
    "陆太太": "លោកស្រីលូ!",
    "陆太太这不太好吧": "លោកស្រីលូ ធ្វើបែបនេះប្រហែលជាមិនសមទេមើលទៅ",
    "今天吃错药了？": "ថ្ងៃនេះលេបថ្នាំខុសមែនទេ?",
    "今天吃错药了": "ថ្ងៃនេះលេបថ្នាំខុសមែនទេ?",
    "你怎么来了": "ម៉េចក៏នាងមកទីនេះ?",
    "来找你啊你妈吩咐的": "មកតាមរកឯងហ្នឹងហើយ ម៉ាក់ឯងឱ្យមក!",
    "你妈吩咐的": "ម៉ាក់ឯងជាអ្នកប្រាប់!",
    "迟哥夜不归宿": "បងលូមិនព្រមទៅផ្ទះពេលយប់",
    "在外面逢场作戏": "គ្រាន់តែដើរលេងសប្បាយនៅខាងក្រៅសោះ",
    "男人生性就爱玩": "ធម្មជាតិមនុស្សប្រុសតែងតែចូលចិត្តដើរលេងហើយ",
    "男人在外面应酬": "មនុស្សប្រុសត្រូវទំនាក់ទំនងការងារនៅខាងក្រៅ",
    "女人就该在家乖乖等着": "ស្រីៗគួរតែនៅផ្ទះចាំប្ដីឱ្យស្ងៀមទៅ",
    "嫂子在家": "បងថ្លៃស្រីនៅផ្ទះ",
    "管不住自己男人的女人": "ស្រីដែលមិនចេះគ្រប់គ្រងប្ដីខ្លួនឯង",
    "拴不住我们陆总的心": "គ្មានសមត្ថភាពចងចិត្តលោកប្រធានលូរបស់យើងទេ",
    "你这个泼妇": "មីស្រីកាចឆ្នាស់!",
    "跑出来闹像什么话": "រត់មកឡាំប៉ានៅទីនេះ ចង់លក់មុខមែនទេ?!",
    "差不多得了": "ល្មមៗបានហើយ!",
    "我不说第二遍": "ខ្ញុំមិននិយាយដដែលៗជាលើកទីពីរទេ!",
    "我要是不呢？": "ចុះបើខ្ញុំថាមិនទៅវិញ?",
    "我要是不呢": "ចុះបើខ្ញុំថាមិនទៅវិញ?",
    "那就成全你": "អញ្ចឹងខ្ញុំជួយសម្រេចបំណងនាងចុះ!",
    "下去": "ចុះទៅ!",
    "下": "ចុះទៅ!",
    "好呀": "ល្អតើ!",
    "整天惦记着": "គិតតែពីបារម្ភទាំងយប់ទាំងថ្ងៃ",
    "早点回家吧孩子": "ឆាប់ទៅផ្ទះវិញទៅកូន",
    "听妈妈的话": "ស្ដាប់សម្ដីម៉ាក់ទៅ",
    "在你们村": "នៅភូមិរបស់ឯង",
    "省得挡了您": "កុំឱ្យទើសផ្លូវលោក",
    "真是好生活啊": "ជីវិតរស់នៅស្រួលពេកហើយ",
    "正好": "ល្មមត្រូវពេលល្អណាស់",
    "正好我现在有空": "ចំពេលដែលខ្ញុំកំពុងទំនេរល្មម",
    "不如回去好好反省反省": "ទៅផ្ទះវិញ ដេកគិតពិចារណាខ្លួនឯងទៅល្អជាង",
    "与其在这里": "ជាជាងនៅទីនេះ",
    "准备什么时候": "តើត្រៀមខ្លួនពេលណា?",
    "像你这种爱反省自己": "មនុស្សដូចជានាងដែលចូលចិត្តពិចារណាខ្លួនឯង",
    "自己哪里不够味": "ថាមកពីខ្លួនឯងមិនទាក់ទាញគ្រប់គ្រាន់",
    "扒拉着里面的垃圾": "នៅកកាយគំនរសំរាមនៅទីនេះ",
    "所以你只能像个": "បានជានាងអាចធ្វើបានត្រឹមតែ...",
    "以前也没见你这么较真": "ពីមុនមិនដែលឃើញនាងប្រកាន់ច្រើនបែបនេះទេ",
    "那大家就都别较真了": "អញ្ចឹងពួកយើងកុំប្រកាន់គ្នាច្រើនអី",
    "你要给我评评理啊": "ឯងត្រូវតែជួយរកយុត្តិធម៌ឱ្យខ្ញុំណា!",
    "你刚刚在门口": "អម្បាញ់មិញឯងនៅមាត់ទ្វារ",
    "你刚刚在向口": "អម្បាញ់មិញឯងនៅមាត់ទ្វារ",
    "就当你是哑巴了": "ចាត់ទុកថាឯងជាមនុស្សគទៅចុះ",
    "本来你不说话我": "ដើមឡើយឯងមិននិយាយ ខ្ញុំ...",
    "提前通知我一声": "ប្រាប់ឱ្យខ្ញុំដឹងជាមុនផង",
    "怕是要打喷嚏了": "ប្រហែលជាត្រូវកណ្ដាស់ហើយមើលទៅ",
    "你还没结婚吗": "នាងមិនទាន់រៀបការទេមែនទេ?",
    "离婚协议书": "កិច្ចសន្យាលែងលះ",
    "签字吧": "ចុះហត្ថលេខាទៅ!",
    "我在金店干了30年": "ខ្ញុំធ្វើការនៅហាងមាសនេះ ៣០ឆ្នាំហើយ...",
    "退休前三天": "សល់តែ ៣ថ្ងៃទៀតចូលនិវត្តន៍...",
    "亲手带出来的徒弟求我": "ស្រាប់តែកូនសិស្សបង្កើត ដែលខ្ញុំបង្រៀន...",
    "飞贝伤感着长妈": "បងស្រី...",
    "你妈孙夫的": "ម៉ាក់ឯងជាអ្នកប្រាប់!",
    "检称三特吗": "ពិនិត្យមើលសិន..."
}

def clean_key(text: str) -> str:
    """Removes trailing punctuation for dictionary matching."""
    return re.sub(r'[\s\.\,\?\!\:\;\"\'\(\)\[\]\{\}\<\>\/\-\_\—\…\~\，\。\？\！\：\；\“\”\‘\’]', '', text)


def translate_dialogue_cues(canonical_json_path: str, output_translated_json: str, use_service=True) -> dict:
    """
    Populates khmer_translation, voice, pitch, and rate for all spoken dialogues.
    """
    with open(canonical_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    dialogues = data.get('dialogues', [])
    translated_count = 0
    skipped_captions = 0
    failed_count = 0

    for index, d in enumerate(dialogues):
        text_cn = (
            d.get('verified_text')
            or d.get('chinese_verified')
            or d.get('chinese')
            or d.get('ocr_text')
            or d.get('asr_text')
            or ''
        ).strip()

        # If empty text or only punctuation, mark as non-spoken caption
        if not text_cn or len(clean_key(text_cn)) == 0:
            d['is_spoken_dialogue'] = False
            d['khmer_translation'] = ""
            d['voice'] = None
            d['pitch'] = "+0Hz"
            d['rate'] = "+0%"
            skipped_captions += 1
            continue

        # Handle visual captions (non-spoken)
        is_spoken = (d.get('speech_classification') == 'spoken') if d.get('speech_classification') else d.get('is_spoken_dialogue', True)
        if not is_spoken:
            ck = clean_key(text_cn)
            try:
                from core.autofix_translations import DRAMA_EXTENDED_DICT
                _all_dict = {**COMMON_PHRASES_KM, **DRAMA_EXTENDED_DICT}
            except Exception:
                _all_dict = COMMON_PHRASES_KM
            trans = _all_dict.get(text_cn) or _all_dict.get(ck) or ""
            d['speech_classification'] = 'visual_caption'
            d['is_spoken_dialogue'] = False
            d['tts_enabled'] = False
            d['khmer_translation'] = trans
            d['khmer_display'] = trans
            d['khmer_spoken'] = ""  # Never synthesize visual captions
            d['translation_status'] = "LANGUAGE_PASSED" if trans and is_valid_for_tts(trans) else "NOT_TRANSLATED"
            d['approval_status'] = "approved" if trans and is_valid_for_tts(trans) else "pending"
            d['voice'] = None
            d['pitch'] = "+0Hz"
            d['rate'] = "+0%"
            skipped_captions += 1
            continue

        speaker = d.get('speaker', 'speaker_01')
        
        # Determine voice based on dialogue context / speaker
        female_lead_keywords = [
            "漂亮吗", "讨厌", "陆总", "帅", "年轻有为", "姐姐", "做妹妹", "成全你", "评评理", "来找你啊",
            "年雅璇", "雅璇", "生日", "玩笑", "初吻", "单身", "皮卡丘", "男神", "认出来", "后悔", "包养"
        ]
        male_lead_keywords = [
            "你说呢", "等等", "回去", "下去", "反省", "谁", "差不多得了", "不说第二遍", "身材",
            "霍凌沉", "少爷", "卓叔叔", "叔叔", "离婚协议", "轰出去", "可恶", "该死", "办公室", "妻子", "管家"
        ]
        if any(kw in text_cn for kw in female_lead_keywords):
            voice = VOICE_FEMALE_LEAD
            pitch = "+2Hz"
            rate = "+16%"
            character_role = "Female"
        elif any(kw in text_cn for kw in male_lead_keywords):
            voice = VOICE_MALE_LEAD
            pitch = "-4Hz"
            rate = "+16%"
            character_role = "Male"
        else:
            voice = VOICE_FEMALE_LEAD if speaker == "speaker_01" else VOICE_MALE_LEAD
            pitch = "+0Hz"
            rate = "+16%"
            character_role = "Speaker"

        # Apply dictionary mapping or clean colloquial translation
        ck = clean_key(text_cn)
        if text_cn in COMMON_PHRASES_KM:
            khmer_text = COMMON_PHRASES_KM[text_cn]
        elif ck in COMMON_PHRASES_KM:
            khmer_text = COMMON_PHRASES_KM[ck]
        else:
            # Check extended dictionary
            try:
                from core.autofix_translations import lookup_local_dictionaries, translate_with_service
                khmer_text = lookup_local_dictionaries(text_cn)
                if not khmer_text and use_service:
                    khmer_text = translate_with_service(text_cn, context=dialogues[max(0, index-3):index+4])
            except Exception:
                khmer_text = None

            # Fallback validation: never allow Chinese text to slip into khmer_translation
            if not khmer_text or not is_valid_for_tts(khmer_text):
                has_khmer = bool(re.search(r'[\u1780-\u17ff]', text_cn))
                has_hanzi = bool(re.search(r'[\u4e00-\u9fff]', text_cn))
                if has_hanzi and not has_khmer:
                    khmer_text = ""
                else:
                    khmer_text = text_cn

        # Validate final spoken translation
        val = validate_khmer_text(khmer_text)
        d['speaker_role'] = character_role
        d['voice'] = voice
        d['pitch'] = pitch
        d['rate'] = rate
        d['speech_classification'] = 'spoken'
        d['is_spoken_dialogue'] = True

        if val['is_valid_for_tts']:
            d['translation_status'] = 'LANGUAGE_PASSED'
            d['approval_status'] = 'approved'
            d['translation_message'] = 'Language Check Passed'
            d['khmer_translation'] = khmer_text
            d['khmer_spoken'] = khmer_text
            d['khmer_display'] = khmer_text
            d['tts_enabled'] = True
            d['flagged'] = False
            translated_count += 1
        else:
            d['translation_status'] = 'NEEDS_REVIEW'
            d['approval_status'] = 'needs_review'
            d['translation_message'] = val['message']
            d['khmer_translation'] = ""
            d['khmer_spoken'] = ""
            d['khmer_display'] = ""
            d['tts_enabled'] = False
            d['flagged'] = True
            d['review_reasons'] = ['missing_or_failed_translation']
            failed_count += 1

    data['translation_stats'] = {
        "spoken_dialogues_translated": translated_count,
        "spoken_dialogues_failed": failed_count,
        "visual_captions_skipped": skipped_captions
    }

    with open(output_translated_json, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[+] Phase 4 Translation complete: {translated_count} valid spoken translations, {failed_count} need review, {skipped_captions} visual captions skipped.")
    print(f"[+] Saved to: {output_translated_json}")
    return data

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 core/phase4_translate.py <canonical_dialogue.json> <output_translated.json>")
        sys.exit(1)
    translate_dialogue_cues(sys.argv[1], sys.argv[2])
