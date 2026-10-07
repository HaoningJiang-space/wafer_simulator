# Python modules


# Custom modules


class VerticalConnector:
    """A class representing a vertical connector between two wafers
    Attributes:
        x (float): The x-coordinate of the center of this connector w.r.t. the center of the reticle (not w.r.t the wafer).
        y (float): The y-coordinate of the center of this connector w.r.t. the center of the reticle (not w.r.t the wafer).
        width (float): The width of the connector.
        height (float): The height of the connector.
    """
    def __init__(self, x : float, y : float, w : float, h : float):
        """Initializes the VerticalConnector with the given parameters.
        Args:
            x (float): The x-coordinate of the connector w.r.t. the reticle.
            y (float): The y-coordinate of the connector w.r.t. the reticle.
            width (float): The width of the connector.
            height (float): The height of the connector.
        """
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    def overlaps(self, other : 'VerticalConnector') -> bool:
        """Checks if this connector overlaps with another connector.
        Args:
            other (VerticalConnector): The other connector to check for overlap.
        Returns:
            bool: True if the connectors overlap, False otherwise.
        """
        return not ((self.x + self.w / 2 <= other.x - other.w / 2) or 
                    (self.x - self.w / 2 >= other.x + other.w / 2) or 
                    (self.y + self.h / 2 <= other.y - other.h / 2) or 
                    (self.y - self.h / 2 >= other.y + other.h / 2))


    def overlaps_exactly(self, other : 'VerticalConnector') -> bool:
        """Checks if this connector exactly overlaps with another connector.
        Args:
            other (VerticalConnector): The other connector to check for exact overlap.
        Returns:
            bool: True if the connectors exactly overlap, False otherwise.
        """
        return (self.x == other.x and self.y == other.y and 
                self.w == other.w and self.h == other.h)
