class SpearAutomationError(Exception):
    """
    Base exception for all errors within SPEAR automation project.
    """
    pass


# Document Reader Exceptions
class DocumentExtractionError(SpearAutomationError):
    """
    Base exception for all document extraction failures.
    """
    pass

class CorruptedDocumentError(DocumentExtractionError):
    """
    Raised when the file exists but MarkItDown fails to read data
    """
    pass

# AI Agent Exceptions
class AgentConfigurationError(SpearAutomationError):
    """
    Raised when the agent lacks required credentials or configuration.
    """
    pass

class AgentExecutionError(SpearAutomationError):
    """
    Raised when the LLM fails to generate or return valid data.
    """
    pass
