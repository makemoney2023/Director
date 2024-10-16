import logging

from spielberg.agents.base import BaseAgent, AgentResponse, AgentResult
from spielberg.core.session import Session, MsgStatus, ImageContent
from spielberg.tools.replicate import flux_dev

logger = logging.getLogger(__name__)


class ImageGenerationAgent(BaseAgent):
    def __init__(self, session: Session, **kwargs):
        self.agent_name = "image_generation"
        self.description = "Agent for image generation using Gen AI models on given prompt and configurations."
        self.parameters = self.get_parameters()
        super().__init__(session=session, **kwargs)

    def __call__(self, prompt: str, *args, **kwargs) -> AgentResponse:
        """
        Process the prompt to generate the image.

        :param str prompt: prompt for image generation.
        :param args: Additional positional arguments.
        :param kwargs: Additional keyword arguments.
        :return: The response containing information about generated image.
        :rtype: AgentResponse
        """
        try:
            # TODO: Integrate other models and drive parameters from input as well
            self.output_message.actions.append("Processing prompt..")
            image_content = ImageContent(
                agent_name=self.agent_name, status=MsgStatus.progress
            )
            image_content.status_message = "Generating image.."
            self.output_message.content.append(image_content)
            self.output_message.push_update()
            flux_output = flux_dev(prompt)
            if not flux_output:
                image_content.status = MsgStatus.error
                image_content.status_message = "Error in generating image."
                self.output_message.publish()
                error_message = "Agent failed with error in replicate."
                return AgentResponse(result=AgentResult.ERROR, message=error_message)
            image_content.image = {"url": flux_output[0].url}
            image_content.status = MsgStatus.success
            image_content.status_message = "Here is your generated image"
            self.output_message.publish()
        except Exception as e:
            logger.exception(f"Error in {self.agent_name}")
            image_content.status = MsgStatus.error
            image_content.status_message = "Error in generating image."
            self.output_message.publish()
            error_message = f"Agent failed with error {e}"
            return AgentResponse(result=AgentResult.ERROR, message=error_message)
        return AgentResponse(
            result=AgentResult.SUCCESS,
            message=f"Agent {self.name} completed successfully.",
            data={},
        )
