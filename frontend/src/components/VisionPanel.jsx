// Bedrock Vision 교차 검증 — 현장 사진 업로드 → 시각적 최종 확진
// 실제 연동 시: analyze()만 S3 presigned 업로드 + API Gateway 경유 Bedrock Vision 호출로 교체
import { useRef, useState } from "react";
import { ImagePlus, Info, Loader2, ScanSearch, X } from "lucide-react";
import { mockVisionResult, VISION_VERDICT_CONFIG } from "../constants.js";

export default function VisionPanel({ eq }) {
  const [imageUrl, setImageUrl] = useState(null);
  const [fileName, setFileName] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState(null);
  const inputRef = useRef(null);

  const handleFile = (file) => {
    if (!file || !file.type.startsWith("image/")) return;
    setImageUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(file);
    });
    setFileName(file.name);
    setResult(null);
  };

  const analyze = () => {
    setAnalyzing(true);
    setTimeout(() => {
      setResult(mockVisionResult(eq));
      setAnalyzing(false);
    }, 1800);
  };

  const verdictCfg = result ? VISION_VERDICT_CONFIG[result.verdict] : null;
  const VerdictIcon = verdictCfg?.icon ?? Info;

  return (
    <div className="bg-card border border-border rounded-xl p-5 space-y-4">
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => handleFile(e.target.files?.[0])}
      />
      {!imageUrl ? (
        <button
          onClick={() => inputRef.current?.click()}
          className="w-full flex flex-col items-center justify-center gap-2 py-8 rounded-lg border border-dashed border-white/15 bg-white/[0.02] hover:border-primary/40 hover:bg-primary/5 transition-colors group"
        >
          <ImagePlus size={22} className="text-muted-foreground group-hover:text-primary transition-colors" />
          <span className="text-xs text-muted-foreground group-hover:text-foreground">
            현장 사진 업로드 (클릭하여 선택)
          </span>
          <span className="text-[10px] text-muted-foreground/60 font-mono">
            스마트폰 촬영 이미지 → Bedrock Vision 교차 검증
          </span>
        </button>
      ) : (
        <div className="space-y-3">
          <div className="relative rounded-lg overflow-hidden border border-border bg-black/30">
            <img src={imageUrl} alt="현장 사진" className="w-full max-h-56 object-contain" />
            <button
              onClick={() => {
                URL.revokeObjectURL(imageUrl);
                setImageUrl(null);
                setFileName("");
                setResult(null);
              }}
              className="absolute top-2 right-2 w-6 h-6 rounded-full bg-black/60 hover:bg-black/80 flex items-center justify-center text-slate-300 hover:text-white transition-colors"
            >
              <X size={12} />
            </button>
            <span className="absolute bottom-2 left-2 text-[10px] font-mono text-slate-300 bg-black/60 px-1.5 py-0.5 rounded">
              {fileName}
            </span>
          </div>
          {!result && (
            <button
              onClick={analyze}
              disabled={analyzing}
              className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-colors ${
                analyzing
                  ? "bg-primary/10 text-primary/60 cursor-wait"
                  : "bg-primary/15 hover:bg-primary/25 text-primary border border-primary/30"
              }`}
            >
              {analyzing ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Bedrock Vision 분석 중...
                </>
              ) : (
                <>
                  <ScanSearch size={14} />
                  Vision 교차 검증 요청
                </>
              )}
            </button>
          )}
        </div>
      )}

      {result && verdictCfg && (
        <div className={`rounded-lg border p-4 ${verdictCfg.cls}`}>
          <div className="flex items-center gap-2 mb-2">
            <VerdictIcon size={14} />
            <span className="text-xs font-bold font-mono">{verdictCfg.label}</span>
            <span className="ml-auto text-[10px] font-mono opacity-60">Claude 3.5 Sonnet Vision</span>
          </div>
          <p className="text-xs leading-relaxed opacity-90">{result.text}</p>
        </div>
      )}
    </div>
  );
}
