class ModelGatewayError(RuntimeError):
    """Base error with a stable category for CoursePilot model routing."""

    category = "model_gateway_error"


class ModelCapabilityError(ModelGatewayError):
    category = "model_capability_error"


class ModelConfigurationError(ModelGatewayError):
    category = "model_configuration_error"


class ToolCallingForbidden(ModelGatewayError):
    category = "tool_calling_forbidden"
