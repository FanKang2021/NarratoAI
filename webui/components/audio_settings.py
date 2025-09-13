import streamlit as st
import os
from uuid import uuid4
from app.config import config
from app.services import voice
from app.models.schema import AudioVolumeDefaults
from app.utils import utils
from webui.utils.cache import get_songs_cache


def get_soulvoice_voices():
    """获取 SoulVoice 语音列表"""
    # 检查是否配置了 SoulVoice API key
    api_key = config.soulvoice.get("api_key", "")
    if not api_key:
        return []

    # 只返回一个 SoulVoice 选项，音色通过输入框自定义
    return ["soulvoice:custom"]


def get_tts_engine_options():
    """获取TTS引擎选项"""
    return {
        "edge_tts": "Edge TTS",
        "azure_speech": "Azure Speech Services",
        "soulvoice": "SoulVoice",
        "local_tts": "本地TTS (离线)"
    }


def get_tts_engine_descriptions():
    """获取TTS引擎详细描述"""
    return {
        "edge_tts": {
            "title": "Edge TTS",
            "features": "完全免费，但服务稳定性一般，不支持语音克隆功能",
            "use_case": "测试和轻量级使用",
            "registration": None
        },
        "azure_speech": {
            "title": "Azure Speech Services",
            "features": "提供一定免费额度，超出后按量付费，需要绑定海外信用卡",
            "use_case": "企业级应用，需要稳定服务",
            "registration": "https://portal.azure.com/#view/Microsoft_Azure_ProjectOxford/CognitiveServicesHub/~/SpeechServices"
        },
        "soulvoice": {
            "title": "SoulVoice",
            "features": "提供免费额度，支持语音克隆，支持微信购买额度，无需信用卡，性价比极高",
            "use_case": "个人用户和中小企业，需要语音克隆功能",
            "registration": "https://soulvoice.scsmtech.cn/"
        },
        "local_tts": {
            "title": "本地TTS (离线)",
            "features": "完全离线，调用本地模型，适合隐私和无外网环境，支持自定义模型",
            "use_case": "本地部署、隐私保护、无外网环境",
            "registration": None
        }
    }


def is_valid_azure_voice_name(voice_name: str) -> bool:
    """检查是否为有效的Azure音色名称格式"""
    if not voice_name or not isinstance(voice_name, str):
        return False

    voice_name = voice_name.strip()

    # Azure音色名称通常格式为: [语言]-[地区]-[名称]Neural
    # 例如: zh-CN-YunzeNeural, en-US-AvaMultilingualNeural
    import re
    pattern = r'^[a-z]{2}-[A-Z]{2}-\w+Neural$'
    return bool(re.match(pattern, voice_name))


def render_audio_panel(tr):
    """渲染音频设置面板"""
    with st.container(border=True):
        st.write(tr("Audio Settings"))

        # 渲染TTS设置
        render_tts_settings(tr)

        # 渲染背景音乐设置
        render_bgm_settings(tr)


def render_tts_settings(tr):
    """渲染TTS(文本转语音)设置"""

    # 1. TTS引擎选择器
    # st.subheader("🎤 TTS引擎选择")

    engine_options = get_tts_engine_options()
    engine_descriptions = get_tts_engine_descriptions()

    # 获取保存的TTS引擎设置
    saved_tts_engine = config.ui.get("tts_engine", "edge_tts")

    # 确保保存的引擎在可用选项中
    if saved_tts_engine not in engine_options:
        saved_tts_engine = "edge_tts"

    # TTS引擎选择下拉框
    selected_engine = st.selectbox(
        "选择TTS引擎",
        options=list(engine_options.keys()),
        format_func=lambda x: engine_options[x],
        index=list(engine_options.keys()).index(saved_tts_engine),
        help="选择您要使用的文本转语音引擎"
    )

    # 保存TTS引擎选择
    config.ui["tts_engine"] = selected_engine

    # 2. 显示引擎详细说明
    if selected_engine in engine_descriptions:
        desc = engine_descriptions[selected_engine]

        with st.expander(f"📋 {desc['title']} 详细说明", expanded=True):
            st.markdown(f"**特点：** {desc['features']}")
            st.markdown(f"**适用场景：** {desc['use_case']}")

            if desc['registration']:
                st.markdown(f"**注册地址：** [{desc['registration']}]({desc['registration']})")

    # 3. 根据选择的引擎渲染对应的配置界面
    # st.subheader("⚙️ 引擎配置")


    if selected_engine == "edge_tts":
        render_edge_tts_settings(tr)
    elif selected_engine == "azure_speech":
        render_azure_speech_settings(tr)
    elif selected_engine == "soulvoice":
        render_soulvoice_engine_settings(tr)
    elif selected_engine == "local_tts":
        # 本地TTS配置（可扩展）
        st.info("本地TTS将调用本地模型，无需配置网络参数。可在下方试听。")
        # 允许自定义voice_name
        local_voice_name = st.text_input("本地TTS音色标识（可选，默认local:default）", value="local:default")
        config.ui["local_voice_name"] = local_voice_name

    # 4. 试听功能
    render_voice_preview_new(tr, selected_engine)


def render_edge_tts_settings(tr):
    """渲染 Edge TTS 引擎设置"""
    # 获取支持的语音列表
    support_locales = ["zh-CN", "en-US"]
    all_voices = voice.get_all_azure_voices(filter_locals=support_locales)

    # 只保留标准版本的语音（Edge TTS专用，不包含V2）
    edge_voices = [v for v in all_voices if "-V2" not in v]

    # 创建友好的显示名称
    friendly_names = {}
    for v in edge_voices:
        friendly_names[v] = v.replace("Female", tr("Female")).replace("Male", tr("Male")).replace("Neural", "")

    # 获取保存的语音设置
    saved_voice_name = config.ui.get("edge_voice_name", "zh-CN-XiaoxiaoNeural-Female")

    # 确保保存的音色在可用列表中
    if saved_voice_name not in friendly_names:
        # 选择与UI语言匹配的第一个语音
        for v in edge_voices:
            if v.lower().startswith(st.session_state.get("ui_language", "zh-CN").lower()):
                saved_voice_name = v
                break
        else:
            # 如果没找到匹配的，使用第一个
            saved_voice_name = edge_voices[0] if edge_voices else ""

    # 音色选择下拉框（Edge TTS音色相对较少，保留下拉框）
    selected_friendly_name = st.selectbox(
        "音色选择",
        options=list(friendly_names.values()),
        index=list(friendly_names.keys()).index(saved_voice_name) if saved_voice_name in friendly_names else 0,
        help="选择Edge TTS音色"
    )

    # 获取实际的语音名称
    voice_name = list(friendly_names.keys())[
        list(friendly_names.values()).index(selected_friendly_name)
    ]

    # 显示音色信息
    with st.expander("💡 Edge TTS 音色说明", expanded=False):
        st.write("**中文音色：**")
        zh_voices = [v for v in edge_voices if v.startswith("zh-CN")]
        for v in zh_voices:
            gender = "女声" if "Female" in v else "男声"
            name = v.replace("-Female", "").replace("-Male", "").replace("zh-CN-", "").replace("Neural", "")
            st.write(f"• {name} ({gender})")

        st.write("")
        st.write("**英文音色：**")
        en_voices = [v for v in edge_voices if v.startswith("en-US")][:5]  # 只显示前5个
        for v in en_voices:
            gender = "女声" if "Female" in v else "男声"
            name = v.replace("-Female", "").replace("-Male", "").replace("en-US-", "").replace("Neural", "")
            st.write(f"• {name} ({gender})")

        if len([v for v in edge_voices if v.startswith("en-US")]) > 5:
            st.write("• ... 更多英文音色")

    config.ui["edge_voice_name"] = voice_name
    config.ui["voice_name"] = voice_name  # 兼容性

    # 音量调节
    voice_volume = st.slider(
        "音量调节",
        min_value=0,
        max_value=100,
        value=int(config.ui.get("edge_volume", 80)),
        step=1,
        help="调节语音音量 (0-100)"
    )
    config.ui["edge_volume"] = voice_volume
    st.session_state['voice_volume'] = voice_volume / 100.0

    # 语速调节
    voice_rate = st.slider(
        "语速调节",
        min_value=0.5,
        max_value=2.0,
        value=config.ui.get("edge_rate", 1.0),
        step=0.1,
        help="调节语音速度 (0.5-2.0倍速)"
    )
    config.ui["edge_rate"] = voice_rate
    st.session_state['voice_rate'] = voice_rate

    # 语调调节
    voice_pitch = st.slider(
        "语调调节",
        min_value=-50,
        max_value=50,
        value=int(config.ui.get("edge_pitch", 0)),
        step=5,
        help="调节语音音调 (-50%到+50%)"
    )
    config.ui["edge_pitch"] = voice_pitch
    # 转换为比例值
    st.session_state['voice_pitch'] = 1.0 + (voice_pitch / 100.0)


def render_azure_speech_settings(tr):
    """渲染 Azure Speech Services 引擎设置"""
    # 服务区域配置
    azure_speech_region = st.text_input(
        "服务区域",
        value=config.azure.get("speech_region", ""),
        placeholder="例如：eastus",
        help="Azure Speech Services 服务区域，如：eastus, westus2, eastasia 等"
    )

    # API Key配置
    azure_speech_key = st.text_input(
        "API Key",
        value=config.azure.get("speech_key", ""),
        type="password",
        help="Azure Speech Services API 密钥"
    )

    # 保存Azure配置
    config.azure["speech_region"] = azure_speech_region
    config.azure["speech_key"] = azure_speech_key

    # 音色名称输入框
    saved_voice_name = config.ui.get("azure_voice_name", "zh-CN-XiaoxiaoMultilingualNeural")

    # 音色名称输入
    voice_name = st.text_input(
        "音色名称",
        value=saved_voice_name,
        help="输入Azure Speech Services音色名称，直接使用官方音色名称即可。例如：zh-CN-YunzeNeural",
        placeholder="zh-CN-YunzeNeural"
    )

    # 显示常用音色示例
    with st.expander("💡 常用音色参考", expanded=False):
        st.write("**中文音色：**")
        st.write("• zh-CN-XiaoxiaoMultilingualNeural (女声，多语言)")
        st.write("• zh-CN-YunzeNeural (男声)")
        st.write("• zh-CN-YunxiNeural (男声)")
        st.write("• zh-CN-XiaochenNeural (女声)")
        st.write("")
        st.write("**英文音色：**")
        st.write("• en-US-AndrewMultilingualNeural (男声，多语言)")
        st.write("• en-US-AvaMultilingualNeural (女声，多语言)")
        st.write("• en-US-BrianMultilingualNeural (男声，多语言)")
        st.write("• en-US-EmmaMultilingualNeural (女声，多语言)")
        st.write("")
        st.info("💡 更多音色请参考 [Azure Speech Services 官方文档](https://docs.microsoft.com/en-us/azure/cognitive-services/speech-service/language-support)")

    # 快速选择按钮
    st.write("**快速选择：**")
    cols = st.columns(3)
    with cols[0]:
        if st.button("中文女声", help="zh-CN-XiaoxiaoMultilingualNeural"):
            voice_name = "zh-CN-XiaoxiaoMultilingualNeural"
            st.rerun()
    with cols[1]:
        if st.button("中文男声", help="zh-CN-YunzeNeural"):
            voice_name = "zh-CN-YunzeNeural"
            st.rerun()
    with cols[2]:
        if st.button("英文女声", help="en-US-AvaMultilingualNeural"):
            voice_name = "en-US-AvaMultilingualNeural"
            st.rerun()

    # 验证音色名称并显示状态
    if voice_name.strip():
        # 检查是否为有效的Azure音色格式
        if is_valid_azure_voice_name(voice_name):
            st.success(f"✅ 音色名称有效: {voice_name}")
        else:
            st.warning(f"⚠️ 音色名称格式可能不正确: {voice_name}")
            st.info("💡 Azure音色名称通常格式为: [语言]-[地区]-[名称]Neural")

    # 保存配置
    config.ui["azure_voice_name"] = voice_name
    config.ui["voice_name"] = voice_name  # 兼容性

    # 音量调节
    voice_volume = st.slider(
        "音量调节",
        min_value=0,
        max_value=100,
        value=int(config.ui.get("azure_volume", 80)),
        step=1,
        help="调节语音音量 (0-100)"
    )
    config.ui["azure_volume"] = voice_volume
    st.session_state['voice_volume'] = voice_volume / 100.0

    # 语速调节
    voice_rate = st.slider(
        "语速调节",
        min_value=0.5,
        max_value=2.0,
        value=config.ui.get("azure_rate", 1.0),
        step=0.1,
        help="调节语音速度 (0.5-2.0倍速)"
    )
    config.ui["azure_rate"] = voice_rate
    st.session_state['voice_rate'] = voice_rate

    # 语调调节
    voice_pitch = st.slider(
        "语调调节",
        min_value=-50,
        max_value=50,
        value=int(config.ui.get("azure_pitch", 0)),
        step=5,
        help="调节语音音调 (-50%到+50%)"
    )
    config.ui["azure_pitch"] = voice_pitch
    # 转换为比例值
    st.session_state['voice_pitch'] = 1.0 + (voice_pitch / 100.0)

    # 显示配置状态
    if azure_speech_region and azure_speech_key:
        st.success("✅ Azure Speech Services 配置已设置")
    elif not azure_speech_region:
        st.warning("⚠️ 请配置服务区域")
    elif not azure_speech_key:
        st.warning("⚠️ 请配置 API Key")


def render_soulvoice_engine_settings(tr):
    """渲染 SoulVoice 引擎设置"""
    # API Key 输入
    api_key = st.text_input(
        "API Key",
        value=config.soulvoice.get("api_key", ""),
        type="password",
        help="请输入您的 SoulVoice API 密钥"
    )

    # 音色 URI 输入
    voice_uri = st.text_input(
        "音色URI",
        value=config.soulvoice.get("voice_uri", "speech:mcg3fdnx:clzkyf4vy00e5qr6hywum4u84:bzznlkuhcjzpbosexitr"),
        help="请输入 SoulVoice 音色标识符",
        placeholder="speech:mcg3fdnx:clzkyf4vy00e5qr6hywum4u84:bzznlkuhcjzpbosexitr"
    )

    # 模型名称选择
    model_options = [
        "FunAudioLLM/CosyVoice2-0.5B",
        "FunAudioLLM/CosyVoice-300M",
        "FunAudioLLM/CosyVoice-300M-SFT",
        "FunAudioLLM/CosyVoice-300M-Instruct"
    ]

    saved_model = config.soulvoice.get("model", "FunAudioLLM/CosyVoice2-0.5B")
    if saved_model not in model_options:
        model_options.append(saved_model)

    model = st.selectbox(
        "模型名称",
        options=model_options,
        index=model_options.index(saved_model),
        help="选择使用的 TTS 模型"
    )

    # 高级设置
    with st.expander("高级设置", expanded=False):
        api_url = st.text_input(
            "API 地址",
            value=config.soulvoice.get("api_url", "https://tts.scsmtech.cn/tts"),
            help="SoulVoice API 接口地址"
        )

    # 保存配置
    config.soulvoice["api_key"] = api_key
    config.soulvoice["voice_uri"] = voice_uri
    config.soulvoice["model"] = model
    config.soulvoice["api_url"] = api_url

    # 设置兼容性配置
    if voice_uri:
        # 确保音色 URI 有正确的前缀
        if not voice_uri.startswith("soulvoice:") and not voice_uri.startswith("speech:"):
            voice_name = f"soulvoice:{voice_uri}"
        else:
            voice_name = voice_uri if voice_uri.startswith("soulvoice:") else f"soulvoice:{voice_uri}"
        config.ui["voice_name"] = voice_name

    # 显示配置状态
    if api_key and voice_uri:
        st.success("✅ SoulVoice 配置已设置")
    elif not api_key:
        st.warning("⚠️ 请配置 SoulVoice API Key")
    elif not voice_uri:
        st.warning("⚠️ 请配置音色 URI")


def render_voice_preview_new(tr, selected_engine):
    """渲染新的语音试听功能"""
    if st.button("🎵 试听语音合成", use_container_width=True):
        play_content = "感谢关注 NarratoAI，有任何问题或建议，可以关注微信公众号，求助或讨论"

        # 根据选择的引擎获取对应的语音配置
        voice_name = ""
        voice_rate = 1.0
        voice_pitch = 1.0

        if selected_engine == "edge_tts":
            voice_name = config.ui.get("edge_voice_name", "zh-CN-XiaoyiNeural-Female")
            voice_rate = config.ui.get("edge_rate", 1.0)
            voice_pitch = 1.0 + (config.ui.get("edge_pitch", 0) / 100.0)
        elif selected_engine == "azure_speech":
            voice_name = config.ui.get("azure_voice_name", "zh-CN-XiaoxiaoMultilingualNeural")
            voice_rate = config.ui.get("azure_rate", 1.0)
            voice_pitch = 1.0 + (config.ui.get("azure_pitch", 0) / 100.0)
        elif selected_engine == "soulvoice":
            voice_uri = config.soulvoice.get("voice_uri", "")
            if voice_uri:
                if not voice_uri.startswith("soulvoice:") and not voice_uri.startswith("speech:"):
                    voice_name = f"soulvoice:{voice_uri}"
                else:
                    voice_name = voice_uri if voice_uri.startswith("soulvoice:") else f"soulvoice:{voice_uri}"
            voice_rate = 1.0  # SoulVoice 使用默认语速
            voice_pitch = 1.0  # SoulVoice 不支持音调调节
        elif selected_engine == "local_tts":
            voice_name = config.ui.get("local_voice_name", "local:default")
            voice_rate = 1.0
            voice_pitch = 1.0

        if not voice_name:
            st.error("请先配置语音设置")
            return

        with st.spinner("正在合成语音..."):
            temp_dir = utils.storage_dir("temp", create=True)
            audio_file = os.path.join(temp_dir, f"tmp-voice-{str(uuid4())}.mp3")

            sub_maker = voice.tts(
                text=play_content,
                voice_name=voice_name,
                voice_rate=voice_rate,
                voice_pitch=voice_pitch,
                voice_file=audio_file,
            )

            if sub_maker and os.path.exists(audio_file):
                st.success("✅ 语音合成成功！")

                # 播放音频
                with open(audio_file, 'rb') as audio_file_obj:
                    audio_bytes = audio_file_obj.read()
                    st.audio(audio_bytes, format='audio/mp3')

                # 清理临时文件
                try:
                    os.remove(audio_file)
                except:
                    pass
            else:
                st.error("❌ 语音合成失败，请检查配置")


def render_azure_v2_settings(tr):
    """渲染Azure V2语音设置（保留兼容性）"""
    saved_azure_speech_region = config.azure.get("speech_region", "")
    saved_azure_speech_key = config.azure.get("speech_key", "")

    azure_speech_region = st.text_input(
        tr("Speech Region"),
        value=saved_azure_speech_region
    )
    azure_speech_key = st.text_input(
        tr("Speech Key"),
        value=saved_azure_speech_key,
        type="password"
    )

    config.azure["speech_region"] = azure_speech_region
    config.azure["speech_key"] = azure_speech_key


def render_soulvoice_settings(tr):
    """渲染 SoulVoice 语音设置（保留兼容性）"""
    saved_api_key = config.soulvoice.get("api_key", "")
    saved_api_url = config.soulvoice.get("api_url", "https://tts.scsmtech.cn/tts")
    saved_model = config.soulvoice.get("model", "FunAudioLLM/CosyVoice2-0.5B")
    saved_voice_uri = config.soulvoice.get("voice_uri", "speech:mcg3fdnx:clzkyf4vy00e5qr6hywum4u84:bzznlkuhcjzpbosexitr")

    # API Key 输入
    api_key = st.text_input(
        "SoulVoice API Key",
        value=saved_api_key,
        type="password",
        help="请输入您的 SoulVoice API 密钥"
    )

    # 音色 URI 输入
    voice_uri = st.text_input(
        "音色 URI",
        value=saved_voice_uri,
        help="请输入 SoulVoice 音色标识符，格式如：speech:mcg3fdnx:clzkyf4vy00e5qr6hywum4u84:bzznlkuhcjzpbosexitr",
        placeholder="speech:mcg3fdnx:clzkyf4vy00e5qr6hywum4u84:bzznlkuhcjzpbosexitr"
    )

    # API URL 输入（可选）
    with st.expander("高级设置", expanded=False):
        api_url = st.text_input(
            "API 地址",
            value=saved_api_url,
            help="SoulVoice API 接口地址"
        )

        model = st.text_input(
            "模型名称",
            value=saved_model,
            help="使用的 TTS 模型"
        )

    # 保存配置
    config.soulvoice["api_key"] = api_key
    config.soulvoice["voice_uri"] = voice_uri
    config.soulvoice["api_url"] = api_url
    config.soulvoice["model"] = model

    # 显示配置状态
    if api_key and voice_uri:
        st.success("✅ SoulVoice 配置已设置")
    elif not api_key:
        st.warning("⚠️ 请配置 SoulVoice API Key")
    elif not voice_uri:
        st.warning("⚠️ 请配置音色 URI")


def render_voice_parameters(tr, voice_name):
    """渲染语音参数设置（保留兼容性）"""
    # 音量 - 使用统一的默认值
    voice_volume = st.slider(
        tr("Speech Volume"),
        min_value=AudioVolumeDefaults.MIN_VOLUME,
        max_value=AudioVolumeDefaults.MAX_VOLUME,
        value=AudioVolumeDefaults.VOICE_VOLUME,
        step=0.01,
        help=tr("Adjust the volume of the original audio")
    )
    st.session_state['voice_volume'] = voice_volume

    # 检查是否为 SoulVoice 引擎
    is_soulvoice = voice.is_soulvoice_voice(voice_name)

    # 语速
    if is_soulvoice:
        # SoulVoice 支持更精细的语速控制
        voice_rate = st.slider(
            tr("Speech Rate"),
            min_value=0.5,
            max_value=2.0,
            value=1.0,
            step=0.1,
            help="SoulVoice 语音速度控制"
        )
    else:
        # Azure TTS 使用预设选项
        voice_rate = st.selectbox(
            tr("Speech Rate"),
            options=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0],
            index=2,
        )
    st.session_state['voice_rate'] = voice_rate

    # 音调 - SoulVoice 不支持音调调节
    if not is_soulvoice:
        voice_pitch = st.selectbox(
            tr("Speech Pitch"),
            options=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0],
            index=2,
        )
        st.session_state['voice_pitch'] = voice_pitch
    else:
        # SoulVoice 不支持音调调节，设置默认值
        st.session_state['voice_pitch'] = 1.0
        st.info("ℹ️ SoulVoice 引擎不支持音调调节")


def render_voice_preview(tr, voice_name):
    """渲染语音试听功能"""
    if st.button(tr("Play Voice")):
        play_content = "感谢关注 NarratoAI，有任何问题或建议，可以关注微信公众号，求助或讨论"
        if not play_content:
            play_content = st.session_state.get('video_script', '')
        if not play_content:
            play_content = tr("Voice Example")

        with st.spinner(tr("Synthesizing Voice")):
            temp_dir = utils.storage_dir("temp", create=True)
            audio_file = os.path.join(temp_dir, f"tmp-voice-{str(uuid4())}.mp3")

            sub_maker = voice.tts(
                text=play_content,
                voice_name=voice_name,
                voice_rate=st.session_state.get('voice_rate', 1.0),
                voice_pitch=st.session_state.get('voice_pitch', 1.0),
                voice_file=audio_file,
            )

            # 如果语音文件生成失败，使用默认内容重试
            if not sub_maker:
                play_content = "This is a example voice. if you hear this, the voice synthesis failed with the original content."
                sub_maker = voice.tts(
                    text=play_content,
                    voice_name=voice_name,
                    voice_rate=st.session_state.get('voice_rate', 1.0),
                    voice_pitch=st.session_state.get('voice_pitch', 1.0),
                    voice_file=audio_file,
                )

            if sub_maker and os.path.exists(audio_file):
                st.success(tr("Voice synthesis successful"))
                st.audio(audio_file, format="audio/mp3")
                if os.path.exists(audio_file):
                    os.remove(audio_file)
            else:
                st.error(tr("Voice synthesis failed"))


def render_bgm_settings(tr):
    """渲染背景音乐设置"""
    # 背景音乐选项
    bgm_options = [
        (tr("No Background Music"), ""),
        (tr("Random Background Music"), "random"),
        (tr("Custom Background Music"), "custom"),
    ]

    selected_index = st.selectbox(
        tr("Background Music"),
        index=1,
        options=range(len(bgm_options)),
        format_func=lambda x: bgm_options[x][0],
    )

    # 获取选择的背景音乐类型
    bgm_type = bgm_options[selected_index][1]
    st.session_state['bgm_type'] = bgm_type

    # 自定义背景音乐处理
    if bgm_type == "custom":
        custom_bgm_file = st.text_input(tr("Custom Background Music File"))
        if custom_bgm_file and os.path.exists(custom_bgm_file):
            st.session_state['bgm_file'] = custom_bgm_file

    # 背景音乐音量 - 使用统一的默认值
    bgm_volume = st.slider(
        tr("Background Music Volume"),
        min_value=AudioVolumeDefaults.MIN_VOLUME,
        max_value=AudioVolumeDefaults.MAX_VOLUME,
        value=AudioVolumeDefaults.BGM_VOLUME,
        step=0.01,
        help=tr("Adjust the volume of the original audio")
    )
    st.session_state['bgm_volume'] = bgm_volume


def get_audio_params():
    """获取音频参数"""
    return {
        'voice_name': config.ui.get("voice_name", ""),
        'voice_volume': st.session_state.get('voice_volume', AudioVolumeDefaults.VOICE_VOLUME),
        'voice_rate': st.session_state.get('voice_rate', 1.0),
        'voice_pitch': st.session_state.get('voice_pitch', 1.0),
        'bgm_type': st.session_state.get('bgm_type', 'random'),
        'bgm_file': st.session_state.get('bgm_file', ''),
        'bgm_volume': st.session_state.get('bgm_volume', AudioVolumeDefaults.BGM_VOLUME),
    }
