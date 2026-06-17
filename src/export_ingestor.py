import os
import json
import glob
from datetime import datetime
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

class JudgeEvaluationSchema(BaseMO)