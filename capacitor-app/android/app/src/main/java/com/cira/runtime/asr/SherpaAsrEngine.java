package com.cira.runtime.asr;

import android.content.Context;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.util.Log;

import com.k2fsa.sherpa.onnx.EndpointConfig;
import com.k2fsa.sherpa.onnx.EndpointRule;
import com.k2fsa.sherpa.onnx.FeatureConfig;
import com.k2fsa.sherpa.onnx.OnlineModelConfig;
import com.k2fsa.sherpa.onnx.OnlineRecognizer;
import com.k2fsa.sherpa.onnx.OnlineRecognizerConfig;
import com.k2fsa.sherpa.onnx.OnlineRecognizerResult;
import com.k2fsa.sherpa.onnx.OnlineStream;
import com.k2fsa.sherpa.onnx.OnlineTransducerModelConfig;

import org.apache.commons.compress.archivers.tar.TarArchiveEntry;
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream;
import org.apache.commons.compress.compressors.bzip2.BZip2CompressorInputStream;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * CIRA 离线语音识别引擎（Sherpa-ONNX）。
 * 替代 Vosk，使用 sherpa-onnx streaming zipformer 模型，识别准确率显著更高。
 * 模型打包在 APK assets 中，首次启动时从 assets 复制到内部存储。
 *
 * 接口与 VoskAsrEngine 完全一致：AsrListener(onPartial / onFinal / onError)。
 */
public class SherpaAsrEngine {

    private static final String TAG = "SherpaAsr";

    // --- 模型配置（int8 量化中文模型，体积小、精度高） ---
    // 模型拆分为两个 asset 文件（各 <100MB，符合 GitHub 文件大小限制），运行时拼接后解压
    private static final String ASSET_PART1 = "models/sherpa-asr-part1.tar.bz2";
    private static final String ASSET_PART2 = "models/sherpa-asr-part2.tar.bz2";
    private static final String MODEL_SUBDIR = "sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30";
    private static final String MODEL_DIR_NAME = "sherpa-asr";
    // 模型文件名（int8 量化版）
    private static final String ENCODER_FILE = "encoder.int8.onnx";
    private static final String DECODER_FILE = "decoder.onnx";
    private static final String JOINER_FILE = "joiner.int8.onnx";
    private static final String TOKENS_FILE = "tokens.txt";

    // --- 音频参数 ---
    private static final int SAMPLE_RATE = 16000;
    private static final int CHANNEL = AudioFormat.CHANNEL_IN_MONO;
    private static final int ENCODING = AudioFormat.ENCODING_PCM_16BIT;

    public interface AsrListener {
        void onPartial(String text);
        void onFinal(String text);
        void onError(String msg);
    }

    public interface ModelReadyCallback {
        void onReady();
        void onError(String msg);
        void onProgress(int percent);
    }

    private final Context ctx;
    private AsrListener listener;
    private OnlineRecognizer recognizer;
    private OnlineStream stream;
    private AudioRecord audioRecord;
    private Thread audioThread;
    private final AtomicBoolean listening = new AtomicBoolean(false);
    private boolean modelReady = false;
    private volatile boolean modelPreparing = false;

    // 兜底机制：stop() 时如果 onFinal 没触发过，用最后一次中间结果兜底
    private volatile boolean finalEmitted = false;
    private volatile String lastPartial = "";
    private final Object lock = new Object();

    public SherpaAsrEngine(Context ctx) {
        this.ctx = ctx.getApplicationContext();
    }

    public void setListener(AsrListener l) {
        this.listener = l;
    }

    public boolean isModelReady() {
        return modelReady;
    }

    /**
     * 异步准备模型（下载 + 解压）。完成后回调 onReady()。
     * 如果模型已在下载中，不会重复触发。
     */
    public void prepareModel(ModelReadyCallback cb) {
        if (modelReady) {
            if (cb != null) cb.onReady();
            return;
        }
        if (modelPreparing) {
            Log.i(TAG, "模型正在下载/初始化中，跳过重复调用");
            return;
        }
        modelPreparing = true;
        new Thread(() -> {
            try {
                File modelDir = new File(ctx.getFilesDir(), MODEL_DIR_NAME);
                File modelSubDir = new File(modelDir, MODEL_SUBDIR);
                File marker = new File(modelDir, ".downloaded");
                File encoder = new File(modelSubDir, ENCODER_FILE);
                File tokens = new File(modelSubDir, TOKENS_FILE);

                if (!marker.exists() || !encoder.exists() || !tokens.exists()) {
                    Log.i(TAG, "Downloading ASR model...");
                    downloadAndExtractModel(modelDir, cb);
                }
                initRecognizer(modelSubDir.getAbsolutePath());
                modelReady = true;
                Log.i(TAG, "ASR model ready");
                if (cb != null) cb.onReady();
            } catch (Exception e) {
                Log.e(TAG, "Model init failed: " + e.getMessage(), e);
                if (cb != null) cb.onError("ASR 模型初始化失败: " + e.getMessage());
            } finally {
                modelPreparing = false;
            }
        }).start();
    }

    private void downloadAndExtractModel(File modelDir, ModelReadyCallback cb) throws IOException {
        modelDir.mkdirs();
        File tarFile = new File(modelDir, "model.tar.bz2");

        // 从 assets 拼接模型文件（part1 + part2 → 完整 tar.bz2）
        Log.i(TAG, "从 assets 拼接 ASR 模型...");
        if (cb != null) cb.onProgress(0);
        try (FileOutputStream out = new FileOutputStream(tarFile)) {
            copyAssetToStream(ASSET_PART1, out, cb, 0, 50);    // part1 占 0-50%
            copyAssetToStream(ASSET_PART2, out, cb, 50, 100);   // part2 占 50-100%
        }
        Log.i(TAG, "模型拼接完成: " + tarFile.length() + " bytes");

        // 解压 tar.bz2
        Log.i(TAG, "解压 ASR 模型...");
        extractTarBz2(tarFile, modelDir);
        tarFile.delete();
        new File(modelDir, ".downloaded").createNewFile();
        Log.i(TAG, "ASR 模型准备完成");
    }

    /**
     * 从 assets 读取数据并写入 OutputStream（流式，不占额外内存）
     */
    private void copyAssetToStream(String assetPath, OutputStream out, ModelReadyCallback cb,
                                    int progressMin, int progressMax) throws IOException {
        try (InputStream in = ctx.getAssets().open(assetPath)) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
            }
        }
        if (cb != null) cb.onProgress(progressMax);
    }

    /**
     * 从 assets 复制文件到内部存储
     */
    private void copyAssetFile(String assetPath, File outputFile, ModelReadyCallback cb) throws IOException {
        Log.i(TAG, "从 assets 复制模型: " + assetPath);
        if (cb != null) cb.onProgress(0);

        try (InputStream in = ctx.getAssets().open(assetPath);
             FileOutputStream out = new FileOutputStream(outputFile)) {
            byte[] buf = new byte[8192];
            int n, total = 0;
            int fileSize = ctx.getAssets().open(assetPath).available();
            int lastPercent = -1;

            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
                total += n;
                if (fileSize > 0) {
                    int percent = (int) (total * 100L / fileSize);
                    if (percent != lastPercent && cb != null) {
                        lastPercent = percent;
                        final int p = percent;
                        new Thread(() -> cb.onProgress(p)).start();
                    }
                }
            }
        }
        Log.i(TAG, "复制完成: " + outputFile.getAbsolutePath());
    }

    private void extractTarBz2(File tarBz2File, File destDir) throws IOException {
        try (FileInputStream fis = new FileInputStream(tarBz2File);
             BufferedInputStream bis = new BufferedInputStream(fis);
             BZip2CompressorInputStream bz2 = new BZip2CompressorInputStream(bis);
             TarArchiveInputStream tar = new TarArchiveInputStream(bz2)) {
            TarArchiveEntry entry;
            while ((entry = tar.getNextTarEntry()) != null) {
                File outFile = new File(destDir, entry.getName());
                if (entry.isDirectory()) {
                    outFile.mkdirs();
                } else {
                    outFile.getParentFile().mkdirs();
                    try (FileOutputStream out = new FileOutputStream(outFile)) {
                        byte[] buf = new byte[8192];
                        int n;
                        while ((n = tar.read(buf)) > 0) out.write(buf, 0, n);
                    }
                }
            }
        }
    }

    private void initRecognizer(String modelDir) {
        OnlineTransducerModelConfig transducer = new OnlineTransducerModelConfig();
        transducer.setEncoder(modelDir + "/" + ENCODER_FILE);
        transducer.setDecoder(modelDir + "/" + DECODER_FILE);
        transducer.setJoiner(modelDir + "/" + JOINER_FILE);

        OnlineModelConfig modelConfig = new OnlineModelConfig();
        modelConfig.setTransducer(transducer);
        modelConfig.setTokens(modelDir + "/" + TOKENS_FILE);
        modelConfig.setNumThreads(2);

        FeatureConfig featConfig = new FeatureConfig();
        featConfig.setSampleRate(SAMPLE_RATE);
        featConfig.setFeatureDim(80);

        // 端点检测：说完自动停
        EndpointRule rule1 = new EndpointRule(false, 2.4f, 0.0f); // 含非静音后停 2.4s
        EndpointRule rule2 = new EndpointRule(true, 1.2f, 0.0f);  // 必须含非静音后停 1.2s
        EndpointRule rule3 = new EndpointRule(false, 0.0f, 20.0f); // 最长 20s
        EndpointConfig endpointConfig = new EndpointConfig(rule1, rule2, rule3);

        OnlineRecognizerConfig config = new OnlineRecognizerConfig();
        config.setFeatConfig(featConfig);
        config.setModelConfig(modelConfig);
        config.setEndpointConfig(endpointConfig);
        config.setEnableEndpoint(true);
        config.setDecodingMethod("greedy_search");
        config.setBlankPenalty(0.5f);

        recognizer = new OnlineRecognizer(null, config);
    }

    /**
     * 开始识别。在后台线程采集麦克风音频并实时送入 sherpa-onnx 流式解码。
     * 如果模型尚未就绪，静默返回（不抛异常）。
     */
    public void start() throws Exception {
        synchronized (lock) {
            if (listening.get()) return;
            if (!modelReady) {
                Log.w(TAG, "模型未就绪，start() 被跳过");
                return;
            }

            finalEmitted = false;
            lastPartial = "";

            stream = recognizer.createStream("");

            int bufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL, ENCODING);
            bufferSize = Math.max(bufferSize, SAMPLE_RATE * 2); // 至少 1 秒缓冲
            audioRecord = new AudioRecord(MediaRecorder.AudioSource.MIC,
                    SAMPLE_RATE, CHANNEL, ENCODING, bufferSize);

            if (audioRecord.getState() != AudioRecord.STATE_INITIALIZED) {
                audioRecord.release();
                audioRecord = null;
                throw new IOException("AudioRecord 初始化失败");
            }

            listening.set(true);
            audioRecord.startRecording();

            audioThread = new Thread(this::processAudioLoop, "sherpa-asr-audio");
            audioThread.start();
        }
    }

    private void processAudioLoop() {
        short[] buf = new short[SAMPLE_RATE / 10]; // 100ms 一帧
        try {
            while (listening.get()) {
                int n = audioRecord.read(buf, 0, buf.length);
                if (n <= 0) continue;

                // short → float 归一化
                float[] samples = new float[n];
                for (int i = 0; i < n; i++) samples[i] = buf[i] / 32768.0f;

                if (stream != null && recognizer != null) {
                    stream.acceptWaveform(samples, SAMPLE_RATE);
                    while (recognizer.isReady(stream)) {
                        recognizer.decode(stream);
                    }

                    OnlineRecognizerResult result = recognizer.getResult(stream);
                    String text = result.getText().trim();

                    if (!text.isEmpty()) {
                        synchronized (lock) { lastPartial = text; }
                        if (listener != null) listener.onPartial(text);
                    }

                    // 端点检测 → 自动发出最终结果
                    if (recognizer.isEndpoint(stream)) {
                        synchronized (lock) {
                            if (!finalEmitted && !text.isEmpty()) {
                                finalEmitted = true;
                                if (listener != null) listener.onFinal(text);
                            }
                        }
                        recognizer.reset(stream);
                    }
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "Audio loop error: " + e.getMessage(), e);
            if (listener != null && listening.get()) {
                listener.onError("音频处理错误: " + e.getMessage());
            }
        }
    }

    /**
     * 停止识别并回传最终结果。
     * 如果 onFinal 还没触发过，用最后一次中间结果兜底。
     */
    public void stop() {
        synchronized (lock) {
            if (!listening.getAndSet(false)) return;
        }

        // 先停音频采集
        try {
            if (audioRecord != null) {
                audioRecord.stop();
                audioRecord.release();
                audioRecord = null;
            }
        } catch (Exception e) {
            Log.w(TAG, "AudioRecord stop error", e);
        }

        // 等音频线程退出
        if (audioThread != null) {
            try { audioThread.join(1000); } catch (InterruptedException ignored) {}
            audioThread = null;
        }

        // 兜底发 onFinal
        synchronized (lock) {
            if (!finalEmitted && lastPartial != null && !lastPartial.isEmpty()) {
                finalEmitted = true;
                if (listener != null) listener.onFinal(lastPartial);
            }
        }

        // 释放 stream
        if (stream != null) {
            try { stream.release(); } catch (Exception ignore) {}
            stream = null;
        }
    }

    public void shutdown() {
        stop();
        synchronized (lock) {
            if (recognizer != null) {
                try { recognizer.release(); } catch (Exception ignore) {}
                recognizer = null;
            }
            modelReady = false;
        }
    }
}
