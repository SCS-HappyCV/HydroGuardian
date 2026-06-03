// case_agent_result 表 Mapper。
// 使用 MyBatis Plus BaseMapper 提供基础增查能力。
package com.hydro.casehub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hydro.casehub.entity.CaseAgentResultEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface CaseAgentResultMapper extends BaseMapper<CaseAgentResultEntity> {
}
