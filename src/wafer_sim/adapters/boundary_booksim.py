"""Same native network with supply/commit commands and packet progress events."""
from wafer_sim.adapters.online_booksim import OnlineBookSim


class BoundaryBookSim(OnlineBookSim):
    def configure(self, *, rx_slots, bounded, streaming=True):
        self._request(dict(command='boundary',cycle=self.now,rx_slots=rx_slots,
                           bounded=bounded,streaming=streaming))
        self.identity.update(rx_slots=rx_slots,bounded=bounded,streaming=streaming)

    def supply(self, identity):
        self._request(dict(command='supply',cycle=self.now,id=identity,flits=1))

    def commit(self, flit):
        self._request(dict(command='commit',cycle=self.now,flit=flit))

    def advance(self, until):
        # Keep the existing all-message checks, while exposing each progress batch.
        self.progress=[]
        return super().advance(until)

    def _receive(self):
        reply=super()._receive()
        if 'progress' in reply: self.progress=reply['progress']
        return reply
