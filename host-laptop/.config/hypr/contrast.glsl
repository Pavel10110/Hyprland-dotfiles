#version 300 es
precision mediump float;
in vec2 v_texcoord;
layout(location = 0) out vec4 fragColor;
uniform sampler2D tex;

void main() {
    vec4 color = texture(tex, v_texcoord);
    
    // ADJUST THIS NUMBER! 
    // 1.0 is normal. 1.2 is 20% more contrast. 1.5 is extreme.
    float contrast = 1.25; 
    
    color.rgb = ((color.rgb - 0.5) * contrast) + 0.5;
    fragColor = color;
}
