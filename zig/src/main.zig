const std = @import("std");

pub const j2534 = @import("j2534.zig");
pub const uds = @import("uds.zig");
pub const protocols = @import("protocols.zig");
pub const exports = @import("exports.zig");

test "PASSTHRU_MSG layout matches C ABI" {
    // According to SAE J2534, PASSTHRU_MSG should be 4152 bytes:
    // 6 * 4 bytes for header + 4128 bytes for data
    try std.testing.expectEqual(@as(usize, 4152), @sizeOf(j2534.PASSTHRU_MSG));
}
