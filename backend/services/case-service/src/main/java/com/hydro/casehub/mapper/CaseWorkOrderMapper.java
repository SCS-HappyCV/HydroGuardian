// 工单表 Mapper。
// 使用 MyBatis Plus BaseMapper 提供基础增改查能力。
package com.hydro.casehub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hydro.casehub.entity.CaseWorkOrderEntity;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface CaseWorkOrderMapper extends BaseMapper<CaseWorkOrderEntity> {
}
