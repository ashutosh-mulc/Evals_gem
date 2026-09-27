# Tag Priority Memory

This file is a **living memory** of tag-to-priority assignments that have led to successful root cause analyses. The agent reads this file at the start of each analysis (Step 2) to leverage past experience, and appends to it after a root cause is verified by the user (Step 7).

## Terminology

- **Agent** — the AI agent/system under test (e.g., Jinju-Gemini-Live, S25-Gemini-Live, S25-GPT-Live, Meta-Live, S25-Claude-Live). One per case.
- **Devices** — the physical devices whose logs were used in the analysis (e.g., Jinju, S25). Multiple per case.

## How This File Works

1. **Before analysis (Step 2):** Read this file. **Filter entries by the current agent** — only use entries where the agent matches. If the issue type and agent match a previous entry, use those tag priorities as a starting point.
2. **During analysis (Steps 2–5):** Assign and adjust priorities based on the current issue. You are not bound to what's in this file — use your judgment.
3. **After verification (Step 7):** Once the user confirms the root cause hypothesis is correct, append the tags that were actually used (the ones that led to the finding) to the matching issue type section below.

## Format

Each entry records:
- **Agent** — which agent the analysis was for (e.g., Jinju-Gemini-Live, S25-Gemini-Live, S25-GPT-Live, Meta-Live, S25-Claude-Live)
- **Devices** — which physical device logs were used (e.g., Jinju, S25)
- **Issue type** — category of the problem
- **Tags that worked** — the P0 tags that led to the verified root cause
- **Root cause summary** — one-line summary of what the issue was
- **Date** — when this entry was added

---

## Verified Tag Priorities

<!-- Entries below are appended by the agent after each successful, user-verified analysis. -->
<!-- Newest entries at the top of each section. -->

### Audio

#### Audio — 2026-09-04

- **Agent:** Jinju-Gemini-Live
- **Devices:** Jinju, S25
- **Issue:** Jinju (Gemini AI) did not respond — no audio response delivered to user. (QID: q00007, vqa_2)
- **Root cause:** Server-side speech detection/endpointing failed to detect user speech. On-device VAD (TinyGemma) ran correctly (NotRecognized — expected for VQA), audio was captured and streamed (GC_AudioRecord active, 0 gRPC errors), BT connection healthy (0 errors). However, server never sent back TRANSCRIBING state. Session stuck at LISTENING — never reached PROCESSING or RESPONDING. Log ended at 21:01:06 with session still in LISTENING (no STOPPED, no inactivity timeout fired within capture window). Same pattern as q266 (2026-08-14): on-device VAD and server-side speech detection are independent systems; on-device VAD worked, server-side speech detection did not. Server connection was healthy (0 errors) — server received audio but never processed speech.
- **P0 tags:** GC_AgentRequestHandlerI, GC_GC_Agent_AIService, GC_TinyGemmaInferenceEn, AIServiceAdapterImpl, LiveAgentSessionImpl, GC_AudioRecord, GC_GrpcClientStatsColle, btaudio_offload_aidl, bluetooth-a2dp, GC_LedDataServiceProtoc, GC_ActivityManagerServi, GC_InputModule, GC_TinyGemmaCommandReco
- **Key differentiators:** ArResponse TRANSCRIBING never received (bad only), ArResponse PROCESSING never received (bad only), ArResponse RESPONDING never received (bad only), ArResponse STOPPED never received (bad only), session stuck at LISTENING until log end (bad only), 0 gRPC errors in both (network healthy), 0 process crashes / 0 binder deaths / 0 BT disconnects (rules out client-side causes), on-device TinyGemma ran in BOTH cases (on-device detection worked), audio capture active in both
- **Multi-device analysis:** Root cause was server-side (Google Gemini Live backend speech detection). S25 (companion phone) functioned correctly — on-device VAD fired, audio captured and streamed via gRPC, healthy connection (0 errors). Jinju (glasses) functioned correctly — PTT button press registered, camera toggle processed, THWART_CHECK initiated. Single-device analysis sufficient to identify state machine stall; multi-device confirmed no BT transport issues.

#### Audio — 2026-08-14

- **Agent:** Jinju-Gemini-Live
- **Devices:** Jinju, S25
- **Issue:** Jinju (Gemini AI) did not respond — no audio response delivered to user. (QID: q266, qa_250_25)
- **Root cause:** Server-side speech detection/endpointing failed to detect user speech. On-device VAD (TinyGemma GC_TinyGemmaCommandReco) correctly detected speech onset (VAD speech onset at 16:58:28.454, #UAD# speech detected rms:4268 at 16:58:28.495), and audio was captured and streamed to server (1097 frames, 0 gRPC errors). However, server never sent back ConversationStateOutput: TRANSCRIBING state (beld tag absent in bad case). No captions returned (1 empty vs 10 with content). Session remained in LISTENING for ~8s after speech detection until client-side inactivity timeout (EXIT_AFTER_USER_INACTIVITY_TIMEOUT) fired. Key clarification: on-device VAD and server-side speech detection are independent systems — on-device VAD is for local command recognition, server-side speech detection drives conversation state machine. On-device VAD worked; server-side speech detection did not. Distinct from q401 (DEADLINE_EXCEEDED) and q26 (QUIC GOAWAY): those had explicit server-side gRPC errors; here server connection was healthy (0 errors) — server received audio but never processed speech.
- **P0 tags:** beld, amal, besx, alwh, bepx, bebx, GC_TinyGemmaCommandReco, GC_TinyGemmaInferenceEn, GC_AgentRequestHandlerI, GC_GC_Agent_AIService, GC_GrpcClientStatsColle, GC_AudioRecord, GC_InputModule, AudioPlaybackService, btaudio_offload_aidl, bluetooth-a2dp
- **Key differentiators:** beld ConversationStateOutput: TRANSCRIBING never received (bad only), [Latency Tracing] User speech starts never logged (bad only), no server captions returned — 1 empty vs 10 with content (bad only), besx State is not idle cancelling inactivity timeout never logged (bad only), on-device VAD fired in BOTH cases (bad and good — on-device detection worked), 0 gRPC errors in both (network healthy), 0 process crashes / 0 binder deaths / 0 BT disconnects (rules out client-side causes)
- **Multi-device analysis:** Root cause was server-side (Google Gemini Live backend speech detection). S25 (companion phone) functioned correctly — on-device VAD fired, audio captured and streamed via gRPC, healthy connection (0 errors). Jinju (glasses) functioned correctly — MIC_ON sound played, BT A2DP link healthy. The on-device VAD (TinyGemma) and server-side speech detection are independent systems. Single-device analysis sufficient to identify state machine stall; multi-device confirmed no BT transport issues.

#### Audio — 2026-07-24

- **Agent:** Jinju-Gemini-Live
- **Devices:** Jinju, S25
- **Issue:** Jinju (Gemini AI) did not respond — no audio response delivered to user. (QID: q446, disfluency_qa_425_25)
- **Root cause:** AGSA (Google Quick Search Box) process on S25 companion phone was killed by ActivityManager due to binder proxy leak (6000 proxies sent to SYSTEM, dominated by IAppSearchObserverProxy x5796). All three AGSA processes (search, googleapp, interactor) killed ~0.4s after session start. binderDied tore down agent session while still in LISTENING state — state machine never reached PROCESSING or RESPONDING. Verified: kill reason was "Too many Binders sent to SYSTEM" (ActivityManager enforcement), NOT an adb command.
- **P0 tags:** GC_TikTokExceptionHandl, GC_ExceptionHandlingExe, libbinder.BpBinder, libbinder.IPCThreadState, ActivityManager, GC_AgentRequestHandlerI, GC_GC_Agent_AIService, GC_AudioRecord, JavaBinder
- **Key differentiators:** "Too many binder proxy objects sent to uid 1000 from uid 10284 (6000 proxies held)" (bad only), "Uid 10284 sent too many Binders to uid 1000" (bad only), "Killing ... googlequicksearchbox" with reason "Too many Binders sent to SYSTEM" (bad only), binderDied / "arStream failed unexpectedly" (bad only), AGSA_EXCEPTION / sendErrorResponse (bad only), state stuck at LISTENING (bad only), "Uncaught exception from runnable" (bad only)
- **Multi-device analysis:** Root cause was on S25 (companion phone) — AGSA binder proxy leak. Jinju (glasses) side was functioning correctly. Good cases (445, 447) never hit the binder proxy limit; sessions progressed LISTENING → PROCESSING → RESPONDING.

#### Audio — 2026-07-24

- **Agent:** Jinju-Gemini-Live
- **Devices:** Jinju, S25
- **Issue:** Jinju (Gemini AI) did not respond — no audio response delivered to user.
- **Root cause:** FATAL EXCEPTION crash of com.android.microxr.projectionclient process on Jinju due to race condition during camera stream teardown. A CAMERA_STATE_TOGGLE (double-press button) triggered stream stop; HEVC encoder codec was released (handleReleaseCodec OK), but a late onOutputBufferAvailable callback fired on CameraEncoder thread and called releaseOutputBuffer() on the already-released MediaCodec, throwing IllegalStateException: codec is released already. Uncaught exception crashed the process (PID 6992). Process death tore down BT data channel to S25 (Channel shutdownNow, 418ms later), device disconnect (441ms), agent session stopped (658ms) while still in LISTENING state — never reached PROCESSING or RESPONDING. After ~5s process restarted and reconnected, but assistant service hit UNIMPLEMENTED errors (ObserveEvents, ObserveHotwordStatus) and no new session was started.
- **P0 tags:** AndroidRuntime, GC_AgentRequestHandlerI, GC_GC_Agent_AIService, GC_BlobDataServiceV1Rem, GC_AssistantClient, GC_AssistantSessionMana, GC_AssistantDataService, GC_AudioRecord, JavaBinder
- **Key differentiators:** FATAL EXCEPTION: CameraEncoder "codec is released already" (bad only), projectionclient process death "has died: pers BFGS" (bad only), Channel shutdownNow invoked (bad only), Device disconnected resetting assistant service (bad only), session stuck at LISTENING → STOPPED (bad only), UNIMPLEMENTED ObserveEvents/ObserveHotwordStatus on reconnect (bad only)
- **Multi-device analysis:** Root cause was on Jinju (glasses) — MediaCodec race condition crash during camera stream teardown. Impact on S25 (companion phone) — BT channel teardown and agent session stop. Good cases (232, 234) never crashed; projectionclient process remained alive and sessions progressed LISTENING → PROCESSING → RESPONDING.

#### Audio — 2026-07-24


- **Agent:** Jinju-Gemini-Live
- **Devices:** Jinju, S25
- **Issue:** Jinju (Gemini AI) did not respond — no audio response delivered to user.
- **Root cause:** AGSA (Google Quick Search Box) process on S25 companion phone was killed by ActivityManager due to binder proxy leak (6000 proxies sent to SYSTEM). All three AGSA processes (search, googleapp, interactor) killed ~0.8s after session start. binderDied tore down agent session while still in LISTENING state — state machine never reached PROCESSING or RESPONDING.
- **P0 tags:** GC_AgentRequestHandlerI, GC_GC_Agent_AIService, GC_TikTokExceptionHandl, GC_ExceptionHandlingExe, GC_AudioRecord
- **Key differentiators:** "Too many Binders sent to SYSTEM" (bad only), "binder proxy objects ... 6000 proxies held" (bad only), "Killing ... googlequicksearchbox" (bad only), binderDied (bad only), state stuck at LISTENING (bad only), "Write audio data to output stream blocked for 10 seconds" (bad only)
- **Multi-device analysis:** Root cause was on S25 (companion phone) — AGSA binder proxy leak. Jinju (glasses) side was functioning correctly. Single-device analysis would have missed the S25-side process kill.

#### Audio — 2026-07-17

- **Agent:** Jinju-Gemini-Live
- **Devices:** Jinju
- **Issue:** Jinju (Gemini AI) did not respond — no audio response delivered to user.
- **Root cause:** Agent state machine hung at PROCESSING state, never transitioned to RESPONDING. AGSA response delivery callback failed to fire. Session never stopped or cleaned up. MediaCodec dead thread errors followed.Agent: Jinju-Gemini-Live
Issue: Jinju responds that it cannot see the image.
Bad Logs: data/results/jinju_gemini_210726/vqa_50_25/eval_set_1/assets/companion_log_00077.txt (S25) and data/results/jinju_gemini_210726/vqa_50_25/eval_set_1/assets/jinju_log_00077.txt (Jinju)
Good logs: You can use 76 and 78 logs as reference.
- **P0 tags:** GC_AgentRequestHandlerI, GC_GC_Agent_AIService, DeliQueue

### Other

#### Other — 2026-08-14

- **Agent:** Jinju-Gemini-Live
- **Devices:** Jinju, S25
- **Issue:** Jinju (Gemini AI) did not respond — TinyGemma misclassified query containing the word "translate" as a Translate command.
- **Root cause:** TinyGemma false-positive "Translate" intent (model output: "translate audio default source unknown target english" → mappedCommand: Translate) launched Google Translate app, which preempted audio focus (AUDIO_FOCUS_LOST) and killed the Gemini Live session while still in TRANSCRIBING — never reached PROCESSING/RESPONDING. Translate app itself then errored out. Good cases correctly classified as "visual" → GeminiEnableCamera and reached RESPONDING.
- **P0 tags:** GC_TinyGemmaCommandReco, GC_TinyGemmaInferenceEn, GC_GC_Agent_AIService, GC_AgentRequestHandlerI, beay, amal, apkc, alwh, GC_InputModule
- **Key differentiators:** model output "translate audio...english" (bad only), mappedCommand: Translate (bad only), AUDIO_FOCUS_LOST (bad only), Google Translate app launch (bad only), apkc user-visible error (bad only), Jinju MCU "Starting activity: Audio Translate" (bad only), state stuck TRANSCRIBING→PAUSED→STOPPED (bad only)
- **Multi-device analysis:** Root cause was on S25 (companion phone) — TinyGemma command misclassification. Impact on Jinju (glasses) — camera stream cancelled, audio capture switched to Translate app's 1-channel pipeline.

### Visual / Vision

#### Visual / Vision — 2026-09-06

- **Agent:** Jinju-Gemini-Live
- **Devices:** Jinju, S25
- **Issue:** Jinju (Gemini AI glasses) could not see image even though shared — AI responded without receiving the image. (QID: q00080, vqa_2)
- **Root cause:** Camera buffer delivery failure during `CaptureFlow.performCapture`. The camera HAL (CamX) produced buffer errors (`errorCode=4/5`, `bufferError=1`, `metadataError=1`) for frames 160–162. The `SettableFuture` tracking the capture result never completed, causing a `TimeoutFutureException` after 5.5s (within the 7000ms `ErrorResilientTaskScheduler` timeout). The error was classified as non-retryable, so no retry was attempted. Unlike good cases where `performCapture` was proactively cancelled with `CancellationException` after ~0.4s and the image was delivered via the streaming path (`GC_CameraServiceProtoco:captureImage` / `FlowCameraService:receiveStream` / `onImageAvailable`), in the bad case **no image was ever delivered** to the AI agent (0 `captureImage` calls, 0 `receiveStream` calls, only 1 `onImageAvailable` which was the thwart check). The AI processed and responded without any visual input.
- **P0 tags:** CaptureFlow, CaptureFlowTask, ErrorResilientTaskScheduler, CameraDeviceClient, CameraDeviceExtension, CamX, Camera3-OutputStream, CameraService, CameraScheduler, Camera3-Device, GC_BlobDataServiceV1Rem, ThwartSession, ThwartAlsHelper, ThwartInputMuxer, ThwartClassifierModel, ThwartTelemetryLogger, GC_AgentRequestHandlerI, AIServiceAdapterImpl, GC_CameraServiceProtoco, FlowCameraService
- **Key differentiators:** `performCapture: Failed to capture` with `TimeoutFutureException` (bad only — good cases had `CancellationException`), camera buffer errors on frames 160-162 with `errorCode=4/5` `bufferError=1` `metadataError=1` (bad only), `SettableFuture status=PENDING` for 5.5s (bad only), 0 `GC_CameraServiceProtoco: captureImage` calls (bad only — good 1 had 10), 0 `FlowCameraService: receiveStream` (bad only — good cases had 1-2), 1 `onImageAvailable` (bad only — good cases had 18-23), `ErrorResilientTaskScheduler: Task failed with non-retryable error: TimeoutFutureException` (bad only — good cases had `CancellationException`), `logPendingState: captureResults 0, images 0` (bad only)
- **Multi-device analysis:** Root cause was on Jinju (glasses) — camera HAL buffer delivery failure during `performCapture`. Impact on S25 (companion phone) — no `captureImage` request was made because the capture path failed before the streaming fallback could be triggered. Good cases (79, 81) had `performCapture` proactively cancelled with `CancellationException` and image delivered via streaming path. The `performCapture` failure itself is common to all cases, but the error type differs: `TimeoutFutureException` (bad — camera never delivered) vs `CancellationException` (good — streaming path took over).

#### Visual / Vision — 2026-08-17

- **Agent:** Jinju-Gemini-Live
- **Devices:** Jinju, S25
- **Issue:** Jinju abruptly ends response with "Goodbye!" — AI only said "Let me take a quick look around. Goodbye." (QID: q152, hqa_150_25)
- **Root cause:** Continuous thwart detection check on Jinju glasses timed out because the camera frame was never delivered to the thwart ML model. The model never ran (all telemetry values = -1: lux=-1, brightness=-1, sensitivity=-1, exposure=-1). The SettableFuture input remained PENDING for ~10s until TimeoutFutureException fired, converted to ThwartException. Treated as UNRECOVERABLE_ERROR — system explicitly decided NOT to recover (maybeTryRecover: Not recovering). Camera stream killed mid-response (STREAMING_PAUSED → STOPPING → STOPPED). Without camera frames, Gemini Live AI terminated response with "Goodbye." Initial thwart check PASSED (model ran, output 7.47E-8, status=1); only the continuous (2nd) check timed out. The thwart detector did NOT crash and did NOT produce a failure result — it simply never received input.
- **P0 tags:** StreamFlowLifecycleManager, StreamFlow, ThwartSession, ContinuousThwartManager, ThwartAlsHelper, ThwartClassifierModel, ThwartTelemetryLogger, ThwartInputMuxer, IntegrityManager, GC_CameraStream, GC_CameraServiceProtoco, GC_CameraStreamManagerI, GC_CameraDevice, GC_AiCameraErrorLoggerI, GC_CameraArbiter, GC_SystemSoundsPlayer, alwh, alts, beld, GC_AgentRequestHandlerI, GC_GrpcClientStatsColle
- **Key differentiators:** ThwartSession TimeoutFutureException with inputFuture PENDING (bad only), ThwartTelemetryLogger status=3 with all values -1 (bad only — model never ran), StreamFlowLifecycleManager "Thwart check failed, streams with privacy indicator will fail" (bad only), maybeTryRecover "Not recovering from error (ThwartException)" (bad only), stopStreamingInternal reason=UNRECOVERABLE_ERROR (bad only), GC_CameraStream receiveStream onError FAILED_PRECONDITION (bad only), ERROR_THWART_CHECK_FAILED (bad only), SYSTEM_SOUND_CAMERA_THWART played (bad only), STOP_GLASSES_GESTURE session cancel (bad only), response "Let me take a quick look around. Goodbye." ~3.2s vs ~10s full response in good cases (bad only), 0 thwart errors in good cases q151/q153
- **Multi-device analysis:** Root cause was on Jinju (glasses) — continuous thwart check timeout (model never received camera frame). Impact on S25 (companion phone) — camera stream gRPC FAILED_PRECONDITION / ERROR_THWART_CHECK_FAILED, thwart alert sound played, session cancelled with STOP_GLASSES_GESTURE. Good cases (q151, q153) had continuous onImageAvailable frames and 0 thwart errors.

#### Visual / Vision — 2026-07-24

- **Agent:** Jinju-Gemini-Live
- **Devices:** Jinju, S25
- **Issue:** Jinju (Gemini AI glasses) claimed it could not see any image — camera image never delivered to AI agent.
- **Root cause:** Second camera pipeline StreamOn attempt on Jinju's IFE (Image Front End) hardware timed out at the kernel level. After transient buffer errors (same as good cases), the system triggered a pipeline re-initialization (ResubmitInitPacket) and issued a 2nd StreamOn with hasFlushOccurred:1. The IFE kernel device (/dev/v4l-subdev1) ioctl timed out ("Connection timed out"), causing fatal CamxResultECSLStreamOn (ErrorCode:32) → errorCode=1 → onHardwareError → stream killed (STREAMING → STOPPING → STOPPED). S25 blob pull then failed (0 packets, NOT_FOUND). Temperature ruled out — good case had higher temps (42.3°C vs 41.5°C) and worked fine.
- **P0 tags:** CamX, CameraDeviceClient, CameraScheduler, StreamFlowLifecycleManager, StreamFlow, GC_BlobDataServiceV1Rem, CameraDeviceExtension, Camera3-OutputStream, GC_CameraServiceProtoco, GlassesCameraDeviceImpl, GC_CameraDevice, CameraService
- **Key differentiators:** 2nd StreamOn with hasFlushOccurred:1 (bad only), CSL IFE ioctl "Connection timed out" on /dev/v4l-subdev1 (bad only), CamxResultECSLStreamOn ErrorCode:32 (bad only), errorCode=1 fatal (bad only), onHardwareError (bad only), STREAMING → STOPPING → STOPPED (bad only), GC_BlobDataServiceV1Rem "error while pulling blob" 0 packets (bad only), NOT_FOUND missing file /photos/9296 (bad only)
- **Multi-device analysis:** Root cause was on Jinju (glasses) — IFE kernel ioctl timeout during 2nd StreamOn. Impact on S25 (companion phone) — blob pull failure. Good cases never triggered a 2nd StreamOn; they recovered from buffer errors within the same pipeline session.

#### Visual / Vision — 2026-07-23

- **Agent:** Jinju-Gemini-Live
- **Devices:** Jinju, S25
- **Issue:** Jinju (Gemini AI glasses) was not able to see the image via camera — camera stream failed to deliver any frames to the AI agent.
- **Root cause:** Thread scheduling race condition on the S25 companion phone. The prewarm camera callback's `startCameraStreamInternal` was delayed by 6ms, firing AFTER the start streaming path had already initiated the stream open. The delayed prewarm callback saw an in-progress stream (`WAITING_FOR_CHANNEL`) and cancelled it (`Cancelling reopenStreamingFuture as a new start request has been received`), tearing down the entire camera stream before the Jinju's `OpenStreamResponse` could be received. Without the S25-side `onCameraStreamStarted` signal, the Jinju's camera stream remained stuck in `STREAMING_PAUSED` state and never transitioned to active `STREAMING` — so no camera frames were delivered to the AI agent.
- **P0 tags:** GC_CameraServiceProtoco, GC_CameraDevice, GlassesCameraDeviceImpl, GC_CameraStreamManagerI, GC_CameraArbiter, StreamFlow, StreamFlowLifecycleManager, CameraService, CameraDeviceClient, CameraDeviceExtension
- **Key differentiators:** `Cancelling reopenStreamingFuture` (bad only), `openStreamOnly is true` (good only), `onCameraStreamStarted` (good only), `onError: Task was cancelled` (bad only), Jinju `STREAMING_PAUSED → STARTING → STREAMING` transition (good only)
- **Multi-device analysis:** Required merging Jinju + S25 logs. Root cause was on S25 (companion phone), but impact was on Jinju (glasses stuck in STREAMING_PAUSED). Single-device analysis would have missed the S25-side cancellation that caused the Jinju-side stall.

### Network

#### Network — 2026-08-17

- **Agent:** Jinju-Gemini-Live
- **Devices:** Jinju, S25
- **Issue:** Incomplete response — Jinju stopped responding mid-response, audio cut short ~0.4s into RESPONDING. (QID: q66, vqa_50_25)
- **Root cause:** BT data channel (gRPC-over-BT) between S25 and Jinju disconnected 176ms after entering RESPONDING. Mass gRPC cascade (ObserveIntents, ObserveBlobs, ObserveImportAvailability, ObserveState, ObserveLightStatus, ReceiveStream, StreamData failed). SecVendorDataChannelManager: `failed to communicate with data channel, aborting` + `EOFException`. GC_BlobDataServiceV1Rem: `Channel shutdownNow invoked`. Session torn down with `stopReason=STOP_GLASSES_GESTURE`. A2DP audio stopped, response truncated to ~0.4s. Reconnected ~2.7s later but conversation lost; UNIMPLEMENTED errors on reconnect. Same pattern as q80. Good cases (Q65, Q67) had no disconnect during RESPONDING.
- **P0 tags:** GC_AgentRequestHandlerI, GC_GC_Agent_AIService, AIServiceAdapterImpl, GC_GrpcClientStatsColle, GC_BlobDataServiceV1Rem, AudioPlaybackService, AudioOrchestratorImpl, btaudio_offload_aidl, bluetooth-a2dp, GC_AudioRecord, GC_GlassesAISessionAudi, ConversationStateReposi, SerializingExecutor, GC_AssistantClient, GC_AssistantDataService, GC_AssistantSessionMana, SecVendorDataChannelManager, GC_TinyGemmaCommandReco, GC_TinyGemmaInferenceEn, GC_InputModule
- **Key differentiators:** Mass `addCallError` cascade for 7+ gRPC methods (bad only), `SecVendorDataChannelManager: failed to communicate with data channel, aborting` + `EOFException` (bad only), `Channel shutdownNow invoked` (bad only), `onChannelUnavailable for observeBlobs` (bad only), `onDeviceDisconnected` (bad only), Jinju `SerializingExecutor: call already closed` 130 errors (bad only), `stopReason=STOP_GLASSES_GESTURE` (bad only), response ~0.4s vs full in good cases (bad only)
- **Multi-device analysis:** BT transport instability between S25 and Jinju. gRPC cascade originated on S25. Impact on both — state machine teardown on S25, SerializingExecutor gRPC server errors on Jinju, A2DP audio stop on both.

#### Network — 2026-08-14

- **Agent:** Jinju-Gemini-Live
- **Devices:** Jinju, S25
- **Issue:** Incomplete response — Gemini Live response audio cut short ~0.5s into RESPONDING phase. (QID: q80, vqa_75_25)
- **Root cause:** Bluetooth data channel (gRPC-over-Bluetooth) between S25 phone and Jinju glasses disconnected 209ms after agent entered RESPONDING state. Mass gRPC stream failure cascade (ObserveLightStatus, ObserveBlobs, ReceiveStream, ObserveState, ObserveImportAvailability, VendorDataChannel/StreamData all ended with `UNAVAILABLE: End of stream or IOException`). GC_StateMachine transitioned DATA_CHANNEL_DISCONNECT → DISCONNECTED → TEARDOWN. Conversation terminated with `stopReason=STOP_GLASSES_GESTURE` (system-initiated, not user). A2DP audio stream suspended and stopped, truncating response. System reconnected (control channel ~1.1s, data channel ~3.1s later) but conversation was already lost. Good cases (Q79, Q81) had no data channel disconnect; full ~20s response delivered.
- **P0 tags:** GC_AgentRequestHandlerI, GC_GC_Agent_AIService, AIServiceAdapterImpl, GC_GrpcClientStatsColle, GC_StateMachine, AudioPlaybackService, AudioOrchestratorImpl, btaudio_offload_aidl, bluetooth-a2dp, GC_BlobDataServiceV1Rem, GC_AudioRecord, GC_GlassesAISessionAudi, ConversationStateReposi, GC_TinyGemmaCommandReco, GC_TinyGemmaInferenceEn, GC_InputModule
- **Key differentiators:** Mass `addCallError` cascade for multiple gRPC methods at 13:43:52.781 (bad only), `UNAVAILABLE: End of stream or IOException` in GC_BlobDataServiceV1Rem (bad only), `GC_StateMachine: DATA_CHANNEL_DISCONNECT → DISCONNECTED` (bad only), `GC_StateMachine: → TEARDOWN after STOP` (bad only), `stopReason=STOP_GLASSES_GESTURE` (bad only), response duration ~0.5s vs ~20s in good cases (bad only), `onChannelUnavailable for observeBlobs` (bad only)
- **Multi-device analysis:** Root cause was Bluetooth transport instability between S25 and Jinju. gRPC cascade originated on S25 (companion phone) where the gRPC client runs. Impact on both devices — state machine teardown on S25, A2DP audio stop on both. Good cases (Q79, Q81) never experienced data channel disconnect during RESPONDING.

#### Network — 2026-07-24

- **Agent:** Jinju-Gemini-Live
- **Devices:** Jinju, S25
- **Issue:** Only part of response heard ("later") — partial audio from local pre-recorded error TTS. (QID: q26, vqa_25_25)
- **Root cause:** Server-side QUIC GOAWAY error (`net::ERR_QUIC_GOAWAY_REQUEST_CAN_BE_RETRIED`, `Retryable=false`) caused `processSession-Live` RPC to fail 84ms after LISTENING. Session went directly to ERROR (`CONNECTION_ERROR`, `NETWORK_DISCONNECTED`) — never reached PROCESSING/RESPONDING. Glasses played local pre-recorded error TTS (sound ID 32, ~4.2s — likely "try again later"), but A2DP BT audio path wasn't ready (83ms startup delay), so only the last word "later" was heard. Distinct from q401 where server generated TTS and streamed it back; here the server connection failed immediately so only local pre-recorded error sound was possible.
- **P0 tags:** arap, bciw, bcrx, GC_AgentRequestHandlerI, AIServiceAdapterImpl, GC_GC_Agent_AIService, AudioPlaybackService, btaudio_offload_aidl, bluetooth-a2dp
- **Key differentiators:** `RPC[processSession-Live]: Failed` (bad only), `ERR_QUIC_GOAWAY_REQUEST_CAN_BE_RETRIED, Retryable=false` (bad only), `#CM# Live session failed` (bad only), `NetworkException: UNAVAILABLE` (bad only), agent state ERROR with CONNECTION_ERROR/NETWORK_DISCONNECTED (bad only), `playSound(id=32)` ~4.2s local error TTS (bad only), A2DP stream start 83ms after error sound (bad only), state stuck at LISTENING → ERROR (bad only)
- **Multi-device analysis:** Root cause was server-side (QUIC GOAWAY). Error cascade originated on S25 (companion phone) where the gRPC client runs. Jinju (glasses) correctly played local error TTS but A2DP BT path wasn't ready. Good cases (Q25, Q27) never hit QUIC GOAWAY; sessions progressed LISTENING → PROCESSING → RESPONDING.

#### Network — 2026-07-24

- **Agent:** Jinju-Gemini-Live
- **Devices:** Jinju, S25
- **Issue:** Jinju (Gemini AI) responded "Try again later" — server-side failure prevented any AI response. (QID: q401, disfluency_qa_400_25)
- **Root cause:** Server-side dependency RPC (`footprints/Footprints.Read`) on Google's Bard backend timed out after 10 seconds (DEADLINE_EXCEEDED), causing the main `processSession-Live` RPC to fail with gRPC INTERNAL status (`BardStatusException: Dependency RPC failed`). This tore down the live session and put the agent into ERROR state (errorType=SERVER_ERROR, stopReason=REQUEST_ERROR). Network channel was reachable (`reachable=true`) — purely a server-side transient issue, not a client/device problem.
- **P0 tags:** arap, bciw, bcrx, GC_AgentRequestHandlerI, AIServiceAdapterImpl, GC_GC_Agent_AIService
- **Key differentiators:** `RPC[processSession-Live]: Failed` (bad only), `DEADLINE_EXCEEDED; footprints/Footprints.Read; Deadline (9.999881424s) expired` (bad only), `#CM# Live session failed` grpcStatusCode=INTERNAL (bad only), `#CM# NetworkException: INTERNAL` (bad only), agent state ERROR with SERVER_ERROR/REQUEST_ERROR (bad only), `Failed to receive response from the AI service!` (bad only), state stuck at LISTENING → ERROR (bad only, never reached PROCESSING/RESPONDING)
- **Multi-device analysis:** Root cause was server-side (Bard backend dependency RPC timeout). Error cascade originated on S25 (companion phone) where the gRPC client runs. Jinju (glasses) side was functioning correctly. Good cases (400, 402) never hit the server timeout; sessions progressed LISTENING → PROCESSING → RESPONDING. GC_BlobDataServiceV1Rem errors were ruled out (present in both bad and good cases).

#### Network — 2026-07-17


- **Agent:** Meta-Live
- **Devices:** S25
- **Issue:** Meta-Live (Meta AI glasses) failed to respond — response audio not delivered to user.
- **Root cause:** Bluetooth link disconnect between phone and glasses (LINKED_DEVICE_DISCONNECTED) ~1.1s after opener TTS finished. BT disconnect/reconnect cycle corrupted the audio stream (189 Unexpected sequenceId errors, 2771ms audioAsrIngestionGap, session state flapping RUNNING↔PAUSED). Server generated TTS response but corrupted stream prevented proper audio delivery; response extraction failed.
- **P0 tags:** StartMmaiSessionCallback, native.assistant (LiveAiSessionState, SessionConnectionHub), DeviceAssistantStreamChannel, LiveAiRpSdkBridge, native.air (InterDeviceNetworkDisconnectedEvent)


### Performance

*(No entries yet.)*

### App Crash

*(No entries yet.)*

### Other

*(No entries yet.)*

---

## Entry Template

When appending a new entry, use this format:

```
#### [Issue Type] — [Date]

- **Agent:** [agent name, e.g., Jinju-Gemini-Live]
- **Devices:** [device names, e.g., Jinju, S25]
- **Issue:** [one-line description of the problem investigated]
- **Root cause:** [one-line summary]
- **P0 tags:** Tag1, Tag2, Tag3
```
