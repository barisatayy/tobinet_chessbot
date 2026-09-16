"""
ai/model.py
-----------
AlphaZero / Maia stili Dual-Head ResNet (Policy & Value Network) mimarisi.
- Girdi: (Batch, 18, 8, 8) tahta tensörü
- Çıktı 1 (Policy): [Batch, 4168] legal hamle olasılık logitleri
- Çıktı 2 (Value):  [Batch, 1] pozisyon kazanma skoru [-1, +1]
"""

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


if HAS_TORCH:

    class ResidualBlock(nn.Module):
        """Standard Residual Block with skip connection."""

        def __init__(self, filters: int = 128):
            super().__init__()
            self.conv1 = nn.Conv2d(
                filters, filters, kernel_size=3, padding=1, bias=False
            )
            self.bn1 = nn.BatchNorm2d(filters)
            self.relu = nn.ReLU(inplace=True)
            self.conv2 = nn.Conv2d(
                filters, filters, kernel_size=3, padding=1, bias=False
            )
            self.bn2 = nn.BatchNorm2d(filters)

        def forward(self, x):
            residual = x
            out = self.relu(self.bn1(self.conv1(x)))
            out = self.bn2(self.conv2(out))
            out += residual
            return self.relu(out)

    class ChessResNet(nn.Module):
        """
        Satranç Yapay Sinir Ağı.
        num_blocks: Residual blok sayısı (varsayılan 6 blok - RTX 3070 için ideal hız/güç dengesi)
        num_filters: Katmanlardaki filtre sayısı (128 filtre)
        """

        def __init__(
            self, num_blocks: int = 6, num_filters: int = 128, num_actions: int = 4168
        ):
            super().__init__()
            self.num_actions = num_actions

            # Giriş bloğu: 18 kanal -> num_filters
            self.input_conv = nn.Sequential(
                nn.Conv2d(18, num_filters, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm2d(num_filters),
                nn.ReLU(inplace=True),
            )

            # Residual omurga (Backbone)
            self.res_blocks = nn.ModuleList(
                [ResidualBlock(num_filters) for _ in range(num_blocks)]
            )

            # Policy Kafası (Hamle Olasılıkları)
            self.policy_conv = nn.Sequential(
                nn.Conv2d(num_filters, 32, kernel_size=1, bias=False),
                nn.BatchNorm2d(32),
                nn.ReLU(inplace=True),
            )
            self.policy_fc = nn.Linear(32 * 8 * 8, num_actions)

            # Value Kafası (Kazanma Değerlendirmesi: -1.0 ile +1.0)
            self.value_conv = nn.Sequential(
                nn.Conv2d(num_filters, 4, kernel_size=1, bias=False),
                nn.BatchNorm2d(4),
                nn.ReLU(inplace=True),
            )
            self.value_fc = nn.Sequential(
                nn.Linear(4 * 8 * 8, 128),
                nn.ReLU(inplace=True),
                nn.Linear(128, 1),
                nn.Tanh(),
            )

        def forward(self, x):
            # x: [Batch, 18, 8, 8]
            out = self.input_conv(x)
            for block in self.res_blocks:
                out = block(out)

            # Policy
            p = self.policy_conv(out)
            p = p.flatten(start_dim=1)
            policy_logits = self.policy_fc(p)

            # Value
            v = self.value_conv(out)
            v = v.flatten(start_dim=1)
            value = self.value_fc(v)

            return policy_logits, value

        def predict(self, tensor_board, legal_mask=None, device="cuda"):
            """Tek bir tahta için çıkarım (inference) yapar."""
            self.eval()
            with torch.no_grad():
                inp = torch.from_numpy(tensor_board).unsqueeze(0).to(device)
                logits, value = self(inp)
                logits = logits.squeeze(0).cpu().numpy()
                val = value.item()

                if legal_mask is not None:
                    # Yasal olmayan hamleleri eksi sonsuz yap
                    logits[~legal_mask] = -1e9

                # Softmax olasılıkları
                exp_l = np.exp(logits - np.max(logits))
                probs = exp_l / np.sum(exp_l)
                return probs, val

else:

    class ChessResNet:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "PyTorch kurulu değil. Lütfen 'pip install torch' çalıştırın."
            )
