package com.cira.runtime.wake;

import android.content.Context;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.util.Log;

import com.k2fsa.sherpa.onnx.FeatureConfig;
import com.k2fsa.sherpa.onnx.KeywordSpotter;
import com.k2fsa.sherpa.onnx.KeywordSpotterConfig;
import com.k2fsa.sherpa.onnx.OnlineModelConfig;
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
 * Sherpa-ONNX 离线唤醒词引擎（替代 Porcupine）。
 * 完全开源（Apache 2.0），无需注册任何账号。
 *
 * 工作流程：
 *  1. 首次启动时从 assets 复制 KWS 模型（~31MB tar.bz2）到内部存储
 *  2. 解压模型文件（encoder/decoder/joiner/tokens/keywords）
 *  3. 初始化 KeywordSpotter，开始麦克风采集 + 关键词检测
 *  4. 检测到唤醒词时回调 listener.onWake()
 *
 * 模型：sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01（中文，3.3M 参数）
 */
public class SherpaKwsEngine {

    private static final String TAG = "SherpaKws";
    private static final String MODEL_DIR_NAME = "sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01";
    private static final int SAMPLE_RATE = 16000;

    public interface Listener {
        void onWake(String phrase);
    }

    public interface ModelReadyCallback {
        void onReady();
        void onError(String msg);
        void onProgress(int percent);
    }

    private final Context ctx;
    private Listener listener;
    private KeywordSpotter kws;
    private AudioRecord audioRecord;
    private Thread processingThread;
    private final AtomicBoolean isRecording = new AtomicBoolean(false);
    private volatile boolean modelReady = false;

    public SherpaKwsEngine(Context ctx, Listener listener) {
        this.ctx = ctx.getApplicationContext();
        this.listener = listener;
    }

    /** 异步准备模型（下载+解压+初始化），完成后回调 */
    public void prepareModel(ModelReadyCallback callback) {
        new Thread(() -> {
            try {
                File modelDir = getModelDir();
                if (!isModelDownloaded(modelDir)) {
                    Log.i(TAG, "模型未下载，开始下载...");
                    downloadAndExtractModel(callback);
                }
                Log.i(TAG, "模型就绪，初始化 KeywordSpotter...");
                initKws(modelDir);
                modelReady = true;
                if (callback != null) callback.onReady();
            } catch (Exception e) {
                Log.e(TAG, "模型准备失败", e);
                if (callback != null) callback.onError(e.getMessage());
            }
        }).start();
    }

    /** 开始唤醒词检测（需先调用 prepareModel） */
    public void start() {
        if (!modelReady || kws == null) {
            Log.w(TAG, "模型未就绪，无法启动");
            return;
        }
        if (isRecording.get()) return;

        if (!initMicrophone()) {
            Log.e(TAG, "麦克风初始化失败");
            return;
        }

        isRecording.set(true);
        audioRecord.startRecording();

        processingThread = new Thread(this::processAudioLoop, "sherpa-kws-audio");
        processingThread.start();
        Log.i(TAG, "唤醒词检测已启动");
    }

    /** 停止检测 */
    public void stop() {
        isRecording.set(false);
        if (processingThread != null) {
            try { processingThread.join(2000); } catch (InterruptedException ignored) {}
            processingThread = null;
        }
        if (audioRecord != null) {
            try {
                audioRecord.stop();
                audioRecord.release();
            } catch (Exception ignored) {}
            audioRecord = null;
        }
        if (kws != null) {
            try { kws.release(); } catch (Exception ignored) {}
            kws = null;
        }
        modelReady = false;
        Log.i(TAG, "唤醒词检测已停止");
    }

    public boolean isModelReady() {
        return modelReady;
    }

    public boolean isListening() {
        return isRecording.get();
    }

    // ========== 内部实现 ==========

    private void initKws(File modelDir) throws Exception {
        String dir = modelDir.getAbsolutePath();
        String keywordsPath = dir + "/keywords.txt";

        // 如果 keywords.txt 不存在，创建默认的
        File kwFile = new File(keywordsPath);
        if (!kwFile.exists() || kwFile.length() == 0) {
            createDefaultKeywords(keywordsPath);
        }

        OnlineModelConfig modelConfig = new OnlineModelConfig();
        OnlineTransducerModelConfig transducer = new OnlineTransducerModelConfig();
        transducer.setEncoder(dir + "/encoder-epoch-12-avg-2-chunk-16-left-64.onnx");
        transducer.setDecoder(dir + "/decoder-epoch-12-avg-2-chunk-16-left-64.onnx");
        transducer.setJoiner(dir + "/joiner-epoch-12-avg-2-chunk-16-left-64.onnx");
        modelConfig.setTransducer(transducer);
        modelConfig.setTokens(dir + "/tokens.txt");
        modelConfig.setModelType("zipformer2");
        modelConfig.setNumThreads(2);

        FeatureConfig featConfig = new FeatureConfig();
        featConfig.setSampleRate(SAMPLE_RATE);
        featConfig.setFeatureDim(80);

        KeywordSpotterConfig config = new KeywordSpotterConfig();
        config.setFeatConfig(featConfig);
        config.setModelConfig(modelConfig);
        config.setKeywordsFile(keywordsPath);
        config.setKeywordsScore(1.5f);
        config.setKeywordsThreshold(0.25f);
        config.setNumTrailingBlanks(2);
        config.setMaxActivePaths(4);

        kws = new KeywordSpotter(null, config);
        Log.i(TAG, "KeywordSpotter 初始化成功");
    }

    /** 创建默认关键词文件（ppinyin 格式） */
    private void createDefaultKeywords(String path) throws IOException {
        // ppinyin 格式：@分隔音节，每个音节=声母+韵母+声调数字
        // 常见中文唤醒词的 ppinyin 表示
        // 注意：具体格式需与模型的 tokens.txt 对齐
        // 这里提供几个常见唤醒词，实际使用时可根据需要修改
        String defaultKeywords =
            // "你好" - ni3 hao3
            "@n i3 h ao3\n" +
            // "你好小星" - ni3 hao3 xiao3 xing1
            "@n i3 h ao3 x iao3 x ing1\n" +
            // "小星你好" - xiao3 xing1 ni3 hao3
            "@x iao3 x ing1 n i3 h ao3\n" +
            // "嘿小星" - hei1 xiao3 xing1
            "@h ei1 x iao3 x ing1\n";

        File kwFile = new File(path);
        kwFile.getParentFile().mkdirs();
        try (FileWriter fw = new FileWriter(kwFile)) {
            fw.write(defaultKeywords);
        }
        Log.i(TAG, "已创建默认关键词文件: " + path);
    }

    private void processAudioLoop() {
        int bufferSize = (int) (0.1 * SAMPLE_RATE); // 100ms buffer
        short[] buffer = new short[bufferSize];

        OnlineStream stream = kws.createStream("");
        if (stream.getPtr() == 0L) {
            Log.e(TAG, "创建 stream 失败");
            isRecording.set(false);
            return;
        }

        Log.i(TAG, "音频处理循环开始");
        while (isRecording.get()) {
            int ret = audioRecord.read(buffer, 0, buffer.length);
            if (ret > 0) {
                // short → float 转换（sherpa-onnx 需要 float 输入）
                float[] samples = new float[ret];
                for (int i = 0; i < ret; i++) {
                    samples[i] = buffer[i] / 32768.0f;
                }
                stream.acceptWaveform(samples, SAMPLE_RATE);

                while (kws.isReady(stream)) {
                    kws.decode(stream);
                    String keyword = kws.getResult(stream).getKeyword();
                    if (keyword != null && !keyword.isEmpty()) {
                        Log.i(TAG, "检测到唤醒词: " + keyword);
                        kws.reset(stream);
                        if (listener != null) {
                            listener.onWake(keyword);
                        }
                    }
                }
            }
        }

        stream.release();
        Log.i(TAG, "音频处理循环结束");
    }

    private boolean initMicrophone() {
        try {
            int bufferSize = AudioRecord.getMinBufferSize(
                    SAMPLE_RATE,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT
            );
            audioRecord = new AudioRecord(
                    MediaRecorder.AudioSource.MIC,
                    SAMPLE_RATE,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT,
                    bufferSize * 2
            );
            return audioRecord.getState() == AudioRecord.STATE_INITIALIZED;
        } catch (Exception e) {
            Log.e(TAG, "麦克风初始化异常", e);
            return false;
        }
    }

    // ========== 模型下载与解压 ==========

    private File getModelDir() {
        return new File(ctx.getFilesDir(), "sherpa-kws/" + MODEL_DIR_NAME);
    }

    private boolean isModelDownloaded(File modelDir) {
        // 检查关键文件是否存在
        String[] required = {
            "encoder-epoch-12-avg-2-chunk-16-left-64.onnx",
            "decoder-epoch-12-avg-2-chunk-16-left-64.onnx",
            "joiner-epoch-12-avg-2-chunk-16-left-64.onnx",
            "tokens.txt"
        };
        for (String f : required) {
            if (!new File(modelDir, f).exists()) return false;
        }
        return true;
    }

    private void downloadAndExtractModel(ModelReadyCallback callback) throws Exception {
        File kwsDir = new File(ctx.getFilesDir(), "sherpa-kws");
        kwsDir.mkdirs();

        // 检查模型是否已解压
        File marker = new File(kwsDir, ".downloaded");
        if (!marker.exists() || !isModelDownloaded(new File(kwsDir, MODEL_DIR_NAME))) {
            // 从 assets 复制 tar.bz2 文件
            File tarFile = new File(kwsDir, "model.tar.bz2");
            copyAssetFile("models/sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01.tar.bz2", tarFile, callback);

            // 解压
            Log.i(TAG, "解压 KWS 模型...");
            extractTarBz2(tarFile, kwsDir);
            tarFile.delete(); // 删除压缩包

            // 写标记
            marker.createNewFile();
            Log.i(TAG, "KWS 模型准备完成");
        }
    }

    /**
     * 从 assets 复制文件到内部存储
     */
    private void copyAssetFile(String assetPath, File outputFile, ModelReadyCallback callback) throws IOException {
        Log.i(TAG, "从 assets 复制模型: " + assetPath);
        if (callback != null) callback.onProgress(0);

        try (InputStream in = ctx.getAssets().open(assetPath);
             FileOutputStream out = new FileOutputStream(outputFile)) {
            byte[] buf = new byte[8192];
            int n, total = 0;
            // 获取文件大小
            int fileSize = ctx.getAssets().open(assetPath).available();
            int lastPercent = -1;

            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
                total += n;
                if (fileSize > 0) {
                    int percent = (int) (total * 100L / fileSize);
                    if (percent != lastPercent && callback != null) {
                        lastPercent = percent;
                        callback.onProgress(percent);
                    }
                }
            }
        }
        Log.i(TAG, "复制完成: " + outputFile.getAbsolutePath());
    }

    private void extractTarBz2(File tarBz2File, File destDir) throws IOException {
        Log.i(TAG, "开始解压模型...");
        try (FileInputStream fis = new FileInputStream(tarBz2File);
             BufferedInputStream bis = new BufferedInputStream(fis);
             BZip2CompressorInputStream bz2In = new BZip2CompressorInputStream(bis);
             TarArchiveInputStream tarIn = new TarArchiveInputStream(bz2In)) {

            TarArchiveEntry entry;
            while ((entry = tarIn.getNextTarEntry()) != null) {
                String name = entry.getName();
                // 安全检查：防止路径穿越攻击
                if (name.contains("..")) continue;

                File outFile = new File(destDir, name);
                if (entry.isDirectory()) {
                    outFile.mkdirs();
                } else {
                    // 确保父目录存在
                    File parent = outFile.getParentFile();
                    if (parent != null && !parent.exists()) parent.mkdirs();

                    try (OutputStream out = new FileOutputStream(outFile)) {
                        byte[] buf = new byte[8192];
                        int len;
                        long remaining = entry.getSize();
                        while (remaining > 0 && (len = tarIn.read(buf, 0,
                                (int) Math.min(buf.length, remaining))) != -1) {
                            out.write(buf, 0, len);
                            remaining -= len;
                        }
                    }
                    // 设置文件可读权限
                    outFile.setReadable(true, false);
                }
            }
        }
        Log.i(TAG, "模型解压完成");
    }
}
