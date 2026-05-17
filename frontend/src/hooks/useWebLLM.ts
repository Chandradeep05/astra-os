import { useState, useRef, useCallback } from "react";
import { CreateMLCEngine, MLCEngine, InitProgressReport } from "@mlc-ai/web-llm";

export function useWebLLM() {
  const [engine, setEngine] = useState<MLCEngine | null>(null);
  const [isInitializing, setIsInitializing] = useState(false);
  const [progress, setProgress] = useState<string>("");
  const engineRef = useRef<MLCEngine | null>(null);

  const initWebLLM = useCallback(async () => {
    if (engineRef.current || isInitializing) return;
    
    setIsInitializing(true);
    try {
      const initProgressCallback = (report: InitProgressReport) => {
        setProgress(report.text);
      };

      // Best balance of speed and size for WebGPU (1.6GB VRAM)
      const selectedModel = "Llama-3.2-1B-Instruct-q4f32_1-MLC"; 
      
      const newEngine = await CreateMLCEngine(selectedModel, {
        initProgressCallback,
      });

      engineRef.current = newEngine;
      setEngine(newEngine);
      setProgress("✅ Neural Engine Loaded. System Online.");
      
      setTimeout(() => setProgress(""), 2500); // Clear progress text after load

    } catch (error) {
      console.error("Failed to initialize WebLLM:", error);
      setProgress("⚠️ Error initializing GPU engine. Ensure WebGPU is supported.");
    } finally {
      setIsInitializing(false);
    }
  }, [isInitializing]);

  return { engine: engineRef.current || engine, isInitializing, progress, initWebLLM };
}
