import datetime
from enum import Enum
from pydantic import BaseModel
from pathlib import Path
from dataclasses import dataclass

# Paths
SOURCE_JATOS        = Path('sourcedata/JATOS')
RAW_DATA            = Path('sourcedata/JATOS/raw_data/')
RESULT_INDEX        = Path(RAW_DATA / 'result_index.tsv')
PROJECT_CONFIG      = Path('code/JATOS/project_config.json')
CODE_JATOS          = Path('code/JATOS/')
TASK_CONFIGS        = Path('code/JATOS/project_configs')
VALIDATED_DATA      = Path('sourcedata/JATOS/validated_data')
VALIDATION_PROTOCOL = Path(VALIDATED_DATA / 'validation_protocol.tsv')
DOWNLOAD_LOG        = Path('code/JATOS/logs/download.log')
VALIDATE_LOG        = Path('code/JATOS/logs/validate.log')

# Download states
DOWNLOADED = 'downloaded'
DOWNLOAD_FAILED   = 'failed'

# Lists
RESULT_INDEX_HEADERS = [
  'study_title', 'result_id', 'result_uuid', 'study_id', 'study_uuid',
  'start_date', 'end_date', 'duration', 'participant_id', 'study_state',
  'downloaded_at', 'download_status',
]

# Regex
REGEX_PROJECT_TITLE  = r'^[^_]+'
REGEX_PROJECT_SES    = r'ses-[^_]+'
REGEX_PROJECT_TASK   = r'task-[^.]+'
REGEX_SUB            = r'sub-([^_]+)'
REGEX_RESULT_RID     = r'rid-([^_]+)'
REGEX_TASK_NAME      = r'^(?:(?!\bv\.\d+(?:\.\d+)*\b).)*'
REGEX_TASK_VERSION   = r'v\.\d+(?:\.\d+)*'
REGEX_PREFIX         = r'[a-z]+-'

# Time
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"

# Get the local timezone
LOCAL_TZ = datetime.datetime.now().astimezone().tzinfo

# ID keys
ID_KEYS = ['pid', 'PID', 'id', 'ID']

# Title keys
TITLE_KEYS = ['test_version']

# ID correction actions
class Action(Enum):
  KEEP = 'keep'
  REASSIGN_ID = 'reassign_id'
  EXCLUDE = 'exclude'

actions = {action.value for action in Action}

# BaseModel
class Metadata(BaseModel):
    TaskName: str
    TaskDescription: str

class VersionConfig(BaseModel):
    mapping: dict[str, str]
    metadata: Metadata

class TaskConfig(BaseModel):
    version: dict[str, VersionConfig]

class Version(BaseModel):
  """Used to find the mapping for a task."""
  mapping: dict[str, str]

class Task(BaseModel):
  """Used to find specific version of a task."""
  version: dict[str, Version]

class Ids(BaseModel):
  """IDs in a project."""
  ids: list[str]

class Project(BaseModel):
  """Used to find all IDs in a project."""
  title: dict[Ids, str]

class ProjectConfig(BaseModel):
  """JSON structure for project config that contains tasks and projects."""
  task: dict[str, Task]
  project: dict[str, Ids] | None = None

# Dataclasses
@dataclass
class StudyInfo:
  """Holds basic information about a study."""
  participant_id: int
  uuid: str
  title: str

@dataclass
class AppConfig:
  """Holds Basic settings for the server and project."""
  base_url: str
  api_token: str
  project_root: Path

@dataclass
class StudyState:
  """Holds the current study's state."""
  study_id:      int | None = None
  study_uuid:    str | None = None
  result_id:     str | None = None
  study_title:   str | None = None
  project_title: str | None = None

@dataclass
class TaskInfo:
  """Holds the current task's info."""
  title: str
  name: str
  version: str

# Exceptions
class ValidationError(Exception):
  """Base class for validation errors."""

class ValidationProtocolHaveMoreRows(ValidationError):
  """Raised when validation protocol have more rows than validation protocol."""

class NewValidationProtocol(ValidationError):
  """Raised when a new validation_protocol.tsv is created in a project."""

class MissingAction(ValidationError):
  """Raised when a action is missing for a line in the validation_protocol.tsv.
  """

class MissingArgument(ValidationError):
  """Raised when an Argument is missing for a action in validation_protocol.tsv.
  """

class WrongAction(ValidationError):
  """Raised when a wrong action is specified in validation_protocol.tsv."""

class FileError(Exception):
  """Base class for file error."""

class BadZipFile(FileError):
  """Raised when a zipfile cannot be opend."""

class JSONDecodeError(FileError):
  """Raised when JSON structure cannot be loaded."""

class NoDataInFile(FileError):
  """Raised when there is only one symbol in data."""

class NoTitleFound(Exception):
  """Raised when no title could be found in data."""

class NoProjectConfig(Exception):
  """Raised when no project config file was found."""
