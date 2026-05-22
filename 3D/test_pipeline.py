import asyncio
import os
import json
import sys
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# Force UTF-8 stdout for Windows
sys.stdout.reconfigure(encoding='utf-8')

import server

async def run_test(prompt: str):
    print("=" * 60)
    print(f"TESTING PROMPT: {prompt}")
    print("=" * 60)
    
    # Initialize shared resources manually
    server.db_client = server.chromadb.PersistentClient(path=server.CHROMA_DB_PATH)
    server.llm = server.ChatGoogleGenerativeAI(
        model=server.LLM_MODEL,
        google_api_key=server.GEMINI_API_KEY,
        temperature=0.2,
    )
    server._planner_chain = server._PLANNER_PROMPT | server.llm
    server._reranker_chain = server._RERANKER_PROMPT | server.llm
    server._explain_chain = server._EXPLAIN_PROMPT | server.llm
    
    async for event_str in server._run_layout_pipeline(prompt, 5.0, 5.0):
        lines = event_str.strip().split("\n")
        event = ""
        data = ""
        for line in lines:
            if line.startswith("event:"):
                event = line.replace("event:", "").strip()
            elif line.startswith("data:"):
                data = line.replace("data:", "").strip()
        
        if event == "progress":
            progress_data = json.loads(data)
            print(f"[Progress Step {progress_data.get('step')}]: {progress_data.get('message')}")
        elif event == "result":
            result_data = json.loads(data)
            print(f"[Result]: \n{json.dumps(result_data, indent=2, ensure_ascii=False)}")
        elif event == "error":
            error_data = json.loads(data)
            print(f"[Error]: {error_data.get('message')}")

async def main():
    await run_test("thiết kế phòng ăn có bàn ăn dài và 4 ghế ăn gỗ")
    await run_test("thiết kế phòng ăn có tủ cabinet sideboard và gương treo tường")

if __name__ == "__main__":
    asyncio.run(main())
